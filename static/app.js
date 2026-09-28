// Client state: the actual per-provider message histories stay on the server.
let conversationId = null;
let activeProvider = null;
const form = document.querySelector('#chat-form');
const prompt = document.querySelector('#prompt');
const send = document.querySelector('#send');
const answers = document.querySelector('#answers');
const mode = document.querySelector('#mode');

function escapeHtml(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; }
function formatInline(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>');
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>').replace(/(?<!_)_([^_]+)_(?!_)/g, '<em>$1</em>');
  return html.replace(/\[([^\]]+)\]\(([^\s)]+)\)/g, (_, label, href) => {
    const decodedHref = href.replace(/&amp;/g, '&');
    return /^(https?:|mailto:)/i.test(decodedHref)
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : label;
  });
}

// A small, safe Markdown renderer for the response formats common to all providers.
function renderMarkdown(text) {
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
  const blocks = []; let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    if (/^```/.test(line)) {
      const language = line.slice(3).trim(); const code = []; index++;
      while (index < lines.length && !/^```/.test(lines[index])) code.push(lines[index++]);
      if (index < lines.length) index++;
      blocks.push(`<pre><code${language ? ` class="language-${escapeHtml(language)}"` : ''}>${escapeHtml(code.join('\n'))}</code></pre>`); continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) { const level = heading[1].length; blocks.push(`<h${level}>${formatInline(heading[2])}</h${level}>`); index++; continue; }
    const list = line.match(/^\s*([-*+]|\d+\.)\s+(.+)$/);
    if (list) {
      const ordered = /\d+\./.test(list[1]); const items = [];
      while (index < lines.length) {
        const item = lines[index].match(/^\s*([-*+]|\d+\.)\s+(.+)$/);
        if (!item || (/\d+\./.test(item[1]) !== ordered)) break;
        items.push(`<li>${formatInline(item[2])}</li>`); index++;
      }
      blocks.push(`<${ordered ? 'ol' : 'ul'}>${items.join('')}</${ordered ? 'ol' : 'ul'}>`); continue;
    }
    if (/^>\s?/.test(line)) {
      const quote = []; while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ''));
      blocks.push(`<blockquote>${quote.map(formatInline).join('<br>')}</blockquote>`); continue;
    }
    const paragraph = [line]; index++;
    while (index < lines.length && lines[index].trim() && !/^```|^(#{1,6})\s+|^\s*([-*+]|\d+\.)\s+|^>\s?/.test(lines[index])) paragraph.push(lines[index++]);
    blocks.push(`<p>${formatInline(paragraph.join('<br>'))}</p>`);
  }
  return blocks.join('');
}

// Text is escaped before markup is added, so model output cannot inject HTML.
function showResults(results) {
  answers.replaceChildren();
  results.forEach(result => {
    const name = result.provider, config = providers[name], card = document.querySelector('#answer-template').content.firstElementChild.cloneNode(true);
    card.dataset.provider = name; card.querySelector('.dot').classList.add(name); card.querySelector('h2').textContent = config.label; card.querySelector('small').textContent = config.model;
    card.querySelector('.answer').innerHTML = renderMarkdown(result.answer || result.error || 'No answer returned.');
    card.querySelector('.continue').onclick = () => choose(name); answers.append(card);
  });
}
// Continue future messages with the selected model's independent conversation history.
async function choose(provider) {
  const response = await fetch('/api/continue', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({conversation_id:conversationId, provider})});
  const data = await response.json(); if (!response.ok) return alert(data.error);
  activeProvider = provider; mode.textContent = `Continuing with ${data.label} · its independent chat history is preserved`;
  document.querySelectorAll('.model-card').forEach(c => c.style.display = c.dataset.provider === provider ? 'flex' : 'none');
  prompt.focus();
}
form.addEventListener('submit', async event => {
  event.preventDefault(); const text = prompt.value.trim(); if (!text) return;
  send.disabled = true; send.textContent = 'Thinking…';
  try { const response = await fetch('/api/chat', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:conversationId,prompt:text})}); const data = await response.json(); if (!response.ok) throw new Error(data.error); conversationId=data.conversation_id; showResults(data.results); prompt.value=''; }
  catch (error) { alert(error.message); } finally {send.disabled=false;send.innerHTML='Send <span>↵</span>';}
});
prompt.addEventListener('keydown', event => {if (event.key==='Enter'&&!event.shiftKey){event.preventDefault();form.requestSubmit();}});
document.querySelector('#new-chat').onclick = async () => { const response=await fetch('/api/reset',{method:'POST'}); conversationId=(await response.json()).conversation_id; activeProvider=null; mode.textContent='Comparison mode · messages go to every selected model'; location.reload(); };
