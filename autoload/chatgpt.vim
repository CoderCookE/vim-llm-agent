" ChatGPT Autoload Core Functions
" This file contains the main API functions for the ChatGPT plugin

" Add the plugin's python3/ directory to Python's sys.path once per session.
" Call this before any heredoc that imports from chatgpt.*
function! chatgpt#ensure_python_path() abort
  python3 << PYEOF
import sys, os, vim
_plugin_dir = vim.eval('expand("<sfile>:p:h:h")')
_python_path = os.path.join(_plugin_dir, 'python3')
if _python_path not in sys.path:
    sys.path.insert(0, _python_path)
PYEOF
endfunction

" Main ChatGPT function - delegates to Python
function! chatgpt#chat(prompt) abort
  " Ensure suppress_display is off for normal chat operations
  if !exists('g:llm_agent_suppress_display') && !exists('g:chat_gpt_suppress_display')
    let g:llm_agent_suppress_display = 0
  endif

  " Track history file size before request for accurate growth calculation
  let project_dir = getcwd()
  let vim_dir = project_dir . '/.vim-llm-agent'
  if !isdirectory(vim_dir)
    let old_dir = project_dir . '/.vim-chatgpt'
    if isdirectory(old_dir)
      let vim_dir = old_dir
    endif
  endif
  let history_file = vim_dir . '/history.txt'
  let g:chatgpt_history_size_before = filereadable(history_file) ? getfsize(history_file) : 0

  python3 << EOF
import vim
from chatgpt.core import chat_gpt
chat_gpt(vim.eval('a:prompt'))
EOF


  " Check if summary needs updating after AI response completes
  let suppress_display = exists('g:llm_agent_suppress_display') ? g:llm_agent_suppress_display : (exists('g:chat_gpt_suppress_display') ? g:chat_gpt_suppress_display : 0)
  if suppress_display == 0
    call chatgpt#summary#check_and_update()
  endif

  " Ensure we're in the chat window at the bottom
  if suppress_display == 0
    let chat_winnr = bufwinnr('gpt-persistent-session')
    if chat_winnr != -1
      execute chat_winnr . 'wincmd w'
      normal! G
      call cursor('$', 1)
      redraw
    endif
  endif
endfunction

" Display ChatGPT responses in a buffer
function! chatgpt#display_response(response, finish_reason, chat_gpt_session_id)
  let response = a:response
  let finish_reason = a:finish_reason
  let chat_gpt_session_id = a:chat_gpt_session_id
  if !bufexists(chat_gpt_session_id)
    let split_dir = exists('g:llm_agent_split_direction') ? g:llm_agent_split_direction : (exists('g:chat_gpt_split_direction') ? g:chat_gpt_split_direction : 'vertical')
    if split_dir ==# 'vertical'
      silent execute winwidth(0)/g:split_ratio.'vnew '. chat_gpt_session_id
    else
      silent execute winheight(0)/g:split_ratio.'new '. chat_gpt_session_id
    endif
    call setbufvar(chat_gpt_session_id, '&buftype', 'nofile')
    call setbufvar(chat_gpt_session_id, '&bufhidden', 'hide')
    call setbufvar(chat_gpt_session_id, '&swapfile', 0)
    setlocal modifiable
    setlocal wrap
    setlocal linebreak
    call setbufvar(chat_gpt_session_id, '&ft', 'markdown')
    call setbufvar(chat_gpt_session_id, '&syntax', 'markdown')
  endif

  if bufwinnr(chat_gpt_session_id) == -1
    let split_dir = exists('g:llm_agent_split_direction') ? g:llm_agent_split_direction : (exists('g:chat_gpt_split_direction') ? g:chat_gpt_split_direction : 'vertical')
    if split_dir ==# 'vertical'
      execute winwidth(0)/g:split_ratio.'vsplit ' . chat_gpt_session_id
    else
      execute winheight(0)/g:split_ratio.'split ' . chat_gpt_session_id
    endif
  endif

  let last_lines = getbufline(chat_gpt_session_id, '$')
  let last_line = empty(last_lines) ? '' : last_lines[-1]

  let new_lines = substitute(last_line . response, '\n', '\r\n\r', 'g')
  let lines = split(new_lines, '\n')

  let clean_lines = []
  for line in lines
    call add(clean_lines, substitute(line, '\r', '', 'g'))
  endfor

  call setbufline(chat_gpt_session_id, '$', clean_lines)

  " Switch to chat window and scroll to bottom, then restore the original window
  let chat_winnr = bufwinnr(chat_gpt_session_id)
  if chat_winnr != -1
    let current_win = winnr()
    execute chat_winnr . 'wincmd w'
    normal! G
    call cursor('$', 1)
    execute "normal! \<C-E>\<C-Y>"
    redraw
    execute current_win . 'wincmd w'
  endif

  " Save to history file if this is a persistent session
  if chat_gpt_session_id ==# 'gpt-persistent-session' && response != ''
    python3 << EOF
import vim
from chatgpt.utils import save_to_history
save_to_history(vim.eval('a:response'))
EOF
  endif
endfunction

" Helper function to capitalize strings
function! chatgpt#capitalize(str)
    return toupper(strpart(a:str, 0, 1)) . tolower(strpart(a:str, 1))
endfunction
