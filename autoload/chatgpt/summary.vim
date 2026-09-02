" ChatGPT Summary Management
" This file handles conversation summary generation and compaction

" Extract cutoff byte position from summary metadata
" Delegates to Python implementation
function! s:get_summary_cutoff(project_dir) abort
    python3 << EOF
import vim
from chatgpt.summary import get_summary_cutoff
cutoff = get_summary_cutoff(vim.eval('a:project_dir'))
vim.command(f'let l:cutoff_result = {cutoff}')
EOF
    return l:cutoff_result
endfunction

" Check if summary needs updating based on history size
function! chatgpt#summary#check_and_update() abort
    let project_dir = getcwd()
    let home = expand('~')

    " Skip if we're in home directory or system directory
    if project_dir ==# home || project_dir ==# '/' || len(project_dir) <= len(home)
        return
    endif

    if project_dir =~# '^\(/tmp\|/var\|/etc\|/usr\|/bin\|/sbin\|/opt\)'
        return
    endif

    " Use new directory name, but check for old one for backwards compatibility
    let vim_dir = project_dir . '/.vim-llm-agent'
    if !isdirectory(vim_dir)
        let old_dir = project_dir . '/.vim-chatgpt'
        if isdirectory(old_dir)
            let vim_dir = old_dir
        endif
    endif

    let history_file = vim_dir . '/history.txt'
    let summary_file = vim_dir . '/summary.md'

    if !filereadable(history_file)
        return
    endif

    let file_size = getfsize(history_file)
    let compaction_size = exists('g:llm_agent_summary_compaction_size') ? g:llm_agent_summary_compaction_size : (exists('g:chat_gpt_summary_compaction_size') ? g:chat_gpt_summary_compaction_size : 76800)
    let cutoff_byte = s:get_summary_cutoff(project_dir)
    let new_content_size = file_size - cutoff_byte

    if new_content_size > compaction_size
        " Calculate actual growth in this session (if tracked)
        let size_before = exists('g:chatgpt_history_size_before') ? g:chatgpt_history_size_before : cutoff_byte
        let actual_growth = file_size - size_before
        let growth_kb = float2nr(actual_growth / 1024)
        let unsummarized_kb = float2nr(new_content_size / 1024)

        " Show both the actual growth and total unsummarized amount for clarity
        if actual_growth > 0 && actual_growth != new_content_size
            echo "Added " . growth_kb . "KB. Total unsummarized: " . unsummarized_kb . "KB. Compacting into summary..."
        else
            echo "Conversation grew by " . unsummarized_kb . "KB. Compacting into summary..."
        endif

        let save_cwd = getcwd()
        execute 'cd ' . fnameescape(project_dir)

        call chatgpt#summary#generate(1)  " 1 = skip plan resume check (automatic compaction)

        execute 'cd ' . fnameescape(save_cwd)
    elseif !filereadable(summary_file) && file_size > 1024
        echo "No conversation summary found. Generating from history..."

        let save_cwd = getcwd()
        execute 'cd ' . fnameescape(project_dir)

        call chatgpt#summary#generate(1)  " 1 = skip plan resume check (automatic compaction)

        execute 'cd ' . fnameescape(save_cwd)
    endif
endfunction

" Generate conversation summary
" Optional argument: skip_plan_check (1 = skip plan resume prompt, 0 = show it)
function! chatgpt#summary#generate(...) abort
  let skip_plan_check = a:0 > 0 ? a:1 : 0

  " Determine which directory to use (new .vim-llm-agent or old .vim-chatgpt for backwards compatibility)
  let project_dir = getcwd()
  let vim_dir = project_dir . '/.vim-llm-agent'
  let dir_name = '.vim-llm-agent'
  if !isdirectory(vim_dir)
    let old_dir = project_dir . '/.vim-chatgpt'
    if isdirectory(old_dir)
      let dir_name = '.vim-chatgpt'
    endif
  endif

  " This function is complex and calls Python code
  " For now, delegate to the main chat function with appropriate prompt
  python3 << EOF
from chatgpt.summary import generate_conversation_summary
generate_conversation_summary()
EOF

  echo "\nConversation summary generated at " . dir_name . "/summary.md"
  echo "You can edit this file to add or modify preferences."

  " Only check for plan resume if this is a manual operation (not automatic compaction)
  if !skip_plan_check
    call s:check_and_resume_plan()
  endif
endfunction

" Check for active plan and offer to resume execution
function! s:check_and_resume_plan() abort
  let project_dir = getcwd()
  let vim_dir = project_dir . '/.vim-llm-agent'
  if !isdirectory(vim_dir)
    let old_dir = project_dir . '/.vim-chatgpt'
    if isdirectory(old_dir)
      let vim_dir = old_dir
    endif
  endif
  
  let plan_file = vim_dir . '/plan.md'
  
  if !filereadable(plan_file)
    return
  endif
  
  " Read the plan
  let plan_lines = readfile(plan_file)
  let plan_text = join(plan_lines, "\n")
  
  " Strip metadata
  let plan_text = substitute(plan_text, '^<!--.*-->\s*\n', '', '')
  
  if empty(trim(plan_text))
    return
  endif
  
  echo "\n"
  echo "═══════════════════════════════════════════════════════════"
  echo "  ACTIVE PLAN DETECTED"
  echo "═══════════════════════════════════════════════════════════"
  echo ""
  echo plan_text
  echo ""
  echo "═══════════════════════════════════════════════════════════"
  
  let choice = inputlist([
        \ '',
        \ 'An active plan was found. Would you like to resume it?',
        \ '',
        \ '1. Yes - Resume plan execution',
        \ '2. No - Keep plan but don''t resume now',
        \ '3. Clear plan - Mark as completed',
        \ '',
        \ 'Choice: '
        \ ])
  
  if choice == 1
    " Resume the plan
    echo "\nResuming plan execution..."
    call chatgpt#chat("Plan approved. Please proceed.")
  elseif choice == 3
    " Clear the plan using Python function
    python3 << EOF
from chatgpt.utils import clear_plan
clear_plan()
EOF
    echo "\nPlan cleared."
  else
    " Keep plan for later
    echo "\nPlan saved. You can resume it later with :Ask Plan approved. Please proceed."
  endif
endfunction
