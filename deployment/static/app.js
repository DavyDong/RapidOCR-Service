const $ = (id) => document.getElementById(id);
let selectedFile, previewUrl, output;
let busy = false;
function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
function clearResult() {
  output = null;
  $('result').value = '';
  $('page-controls').hidden = true;
  $('page-select').replaceChildren();
  $('copy').disabled = $('download').disabled = true;
}
function selectFile(file) {
  if (!file || busy) return;
  if (file.size > 10 * 1024 * 1024) { status('文件不能超过 10 MB。', true); return; }
  selectedFile = file;
  clearResult();
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  $('preview').removeAttribute('src');
  const pdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
  const tiff = file.type === 'image/tiff' || /\.tiff?$/i.test(file.name);
  $('preview-wrap').hidden = pdf || tiff;
  $('document-preview').hidden = !pdf && !tiff;
  $('document-kind').textContent = pdf ? 'PDF 文档已就绪' : 'TIFF 图片已就绪';
  if (!pdf && !tiff) {
    previewUrl = URL.createObjectURL(file);
    $('preview').src = previewUrl;
  }
  document.querySelector('.upload-panel').classList.add('has-image');
  $('file-name').textContent = file.name;
  $('recognize').disabled = false;
  $('metrics').textContent = '准备就绪';
  status('文件已准备好，点击“开始识别”。');
}
$('image-file').addEventListener('change', (event) => selectFile(event.target.files[0]));
$('dropzone').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!busy) $('image-file').click(); }
});
for (const type of ['dragover', 'dragleave', 'drop']) {
  $('dropzone').addEventListener(type, (event) => {
    event.preventDefault();
    $('dropzone').classList.toggle('dragging', type === 'dragover');
    if (type === 'drop') selectFile(event.dataTransfer.files[0]);
  });
}
for (const [id, path, name, type] of [
  ['sample', '/sample.jpg', '示例图片.jpg', 'image/jpeg'],
  ['sample-pdf', '/sample.pdf', '示例文档.pdf', 'application/pdf'],
]) {
  $(id).addEventListener('click', async () => {
    try {
      const response = await fetch(path);
      if (!response.ok) throw new Error('示例文件加载失败。');
      selectFile(new File([await response.blob()], name, {type}));
    } catch (error) { status(error.message, true); }
  });
}
function showPage() {
  if (!output) return;
  const index = $('page-select').value;
  const page = index === 'all' ? null : output.page_results[Number(index)];
  $('result').value = page ? page.text : output.text;
  $('copy').disabled = !$('result').value;
  $('metrics').textContent = page
    ? `第 ${page.page_number} 页 · ${page.lines.length} 行 · ${page.method === 'native' ? '直接提取' : 'OCR'}`
    : `${output.pages} 页 · ${output.lines.length} 行 · ${output.elapsed_seconds.toFixed(2)} 秒`;
}
$('page-select').addEventListener('change', showPage);
$('recognize').addEventListener('click', async () => {
  if (!selectedFile || busy) return;
  const accessToken = $('access-token').value.trim();
  if (!accessToken) { status('请输入访问令牌后再开始识别。', true); $('access-token').focus(); return; }
  busy = true;
  for (const id of ['recognize', 'image-file', 'sample', 'sample-pdf', 'copy', 'download', 'access-token', 'force-ocr']) $(id).disabled = true;
  clearResult();
  status('正在处理，多页 PDF 可能需要较长时间…');
  $('metrics').textContent = '处理中';
  try {
    const data = new FormData();
    data.append('file', selectedFile);
    data.append('force_ocr', $('force-ocr').checked ? 'true' : 'false');
    const response = await fetch('/api/ocr', {method: 'POST', headers: {Authorization: `Bearer ${accessToken}`}, body: data});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '识别请求失败。');
    output = result;
    $('page-select').add(new Option('全部页面', 'all'));
    result.page_results.forEach((page, index) => {
      $('page-select').add(new Option(`第 ${page.page_number} 页 · ${page.method === 'native' ? '直接提取' : 'OCR'}${page.lines.length ? '' : ' · 无文字'}`, String(index)));
    });
    $('page-controls').hidden = result.type !== 'pdf';
    showPage();
    status(result.lines.length ? '识别完成，可以复制当前文字或下载全部页面的 JSON。' : '未检测到文字，请检查文件内容和清晰度。');
    $('download').disabled = false;
  } catch (error) { status(error.message || '识别失败，请重试。', true); $('metrics').textContent = '识别失败'; }
  finally { busy = false; for (const id of ['recognize', 'image-file', 'sample', 'sample-pdf', 'access-token', 'force-ocr']) $(id).disabled = false; }
});
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('result').value); status('文字已复制。'); }
  catch { $('result').focus(); $('result').select(); status('请按 Ctrl+C 复制选中的文字。'); }
});
$('download').addEventListener('click', () => {
  if (!output) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'rapidocr-result.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
