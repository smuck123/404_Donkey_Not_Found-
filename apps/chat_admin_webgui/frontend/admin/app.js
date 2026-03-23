function $(id) { return document.getElementById(id); }
function setStatus(id, message, isError = false) {
  const el = $(id);
  el.textContent = message;
  el.classList.toggle('error', isError);
}
async function api(url, method = 'GET', body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
  return data;
}
function currentRepo() { return $('repoList').value; }
function currentRepoFile() { return $('repoFiles').value; }
async function loadRepos() {
  const data = await api('/repo/list');
  $('repoList').innerHTML = (data.repos || []).map(repo => `<option value="${repo}">${repo}</option>`).join('');
}
async function testRepo() {
  try {
    const data = await api('/repo/test', 'POST', { repo_url: $('repoUrl').value.trim(), repo_name: $('repoName').value.trim() || null });
    setStatus('repoStatus', `Repo URL OK via ${data.git_bin}.`);
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function cloneRepo() {
  try {
    const data = await api('/repo/clone', 'POST', { repo_url: $('repoUrl').value.trim(), repo_name: $('repoName').value.trim() || null });
    setStatus('repoStatus', `${data.status}: ${data.repo_name}`);
    await loadRepos();
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function loadRepoFiles() {
  try {
    const repo = currentRepo();
    const data = await api(`/repo/files?repo_name=${encodeURIComponent(repo)}`);
    $('repoFiles').innerHTML = (data.files || []).map(file => `<option value="${file}">${file}</option>`).join('');
    setStatus('repoStatus', `Loaded ${data.files.length} files from ${repo}.`);
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function openRepoFile() {
  try {
    const data = await api('/repo/read', 'POST', { repo_name: currentRepo(), relative_path: currentRepoFile() });
    $('repoContent').value = data.content || '';
    setStatus('repoStatus', `Opened ${data.path}.`);
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function saveRepoFile() {
  try {
    await api('/repo/save', 'POST', { repo_name: currentRepo(), relative_path: currentRepoFile(), content: $('repoContent').value });
    setStatus('repoStatus', `Saved ${currentRepoFile()}.`);
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function pullRepo() {
  try {
    const data = await api(`/repo/pull?repo_name=${encodeURIComponent(currentRepo())}`, 'POST');
    setStatus('repoStatus', data.output || `${data.repo_name} updated.`);
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function saveTemplatePack() {
  try {
    const payload = { repo_name: currentRepo(), template_name: $('templateNameInput').value.trim(), selected_files: [] };
    await api('/repo/template/save', 'POST', payload);
    setStatus('repoStatus', 'Template pack saved.');
    await loadTemplates();
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
async function loadTemplates() {
  const data = await api('/repo/templates');
  $('templateList').innerHTML = (data.templates || []).map(item => `<option value="${item.template_name}">${item.template_name} (${item.file_count} files)</option>`).join('');
}
async function showTemplateFiles() {
  try {
    const name = $('templateList').value;
    const data = await api(`/repo/template/files?template_name=${encodeURIComponent(name)}`);
    $('templatePreview').textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    $('templatePreview').textContent = error.message;
  }
}
async function loadSiteFiles() {
  try {
    const section = $('sectionSelect').value;
    const data = await api(`/admin/files?section=${encodeURIComponent(section)}`);
    $('siteFiles').innerHTML = (data.files || []).map(file => `<option value="${file}">${file}</option>`).join('');
    setStatus('siteStatus', `Loaded ${data.files.length} ${section} files.`);
  } catch (error) {
    setStatus('siteStatus', error.message, true);
  }
}
async function openSiteFile() {
  try {
    const section = $('sectionSelect').value;
    const relative_path = $('siteFiles').value;
    const data = await api('/admin/read', 'POST', { section, relative_path });
    $('siteContent').value = data.content || '';
    setStatus('siteStatus', `Opened ${relative_path}.`);
  } catch (error) {
    setStatus('siteStatus', error.message, true);
  }
}
async function saveSiteFile() {
  try {
    const section = $('sectionSelect').value;
    const relative_path = $('siteFiles').value;
    await api('/admin/save', 'POST', { section, relative_path, content: $('siteContent').value });
    setStatus('siteStatus', `Saved ${relative_path}.`);
  } catch (error) {
    setStatus('siteStatus', error.message, true);
  }
}
async function boot() {
  try {
    await Promise.all([loadRepos(), loadTemplates(), loadSiteFiles()]);
  } catch (error) {
    setStatus('repoStatus', error.message, true);
  }
}
$('testRepoBtn').addEventListener('click', testRepo);
$('cloneRepoBtn').addEventListener('click', cloneRepo);
$('refreshReposBtn').addEventListener('click', loadRepos);
$('loadRepoFilesBtn').addEventListener('click', loadRepoFiles);
$('openRepoFileBtn').addEventListener('click', openRepoFile);
$('saveRepoFileBtn').addEventListener('click', saveRepoFile);
$('pullRepoBtn').addEventListener('click', pullRepo);
$('saveTemplatePackBtn').addEventListener('click', saveTemplatePack);
$('refreshTemplatesBtn').addEventListener('click', loadTemplates);
$('showTemplateFilesBtn').addEventListener('click', showTemplateFiles);
$('loadSiteFilesBtn').addEventListener('click', loadSiteFiles);
$('openSiteFileBtn').addEventListener('click', openSiteFile);
$('saveSiteFileBtn').addEventListener('click', saveSiteFile);
boot();
