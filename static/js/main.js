const loginScreen = document.getElementById('loginScreen');
const dashboard = document.getElementById('dashboard');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const showLoginBtn = document.getElementById('showLoginBtn');
const showRegisterBtn = document.getElementById('showRegisterBtn');
const authMessage = document.getElementById('authMessage');
const sidebarAuthBtn = document.getElementById('sidebarAuthBtn');
const userChip = document.getElementById('userChip');
const profileForm = document.getElementById('profileForm');
const passwordForm = document.getElementById('passwordForm');
const alertEmailForm = document.getElementById('alertEmailForm');
const profileMessage = document.getElementById('profileMessage');
const passwordMessage = document.getElementById('passwordMessage');
const alertEmailMessage = document.getElementById('alertEmailMessage');
const navItems = document.querySelectorAll('.nav-item[data-page]');
const pages = document.querySelectorAll('.page');
const videoFeed = document.getElementById('videoFeed');
const overlayCanvas = document.getElementById('overlayCanvas');
const overlayCtx = overlayCanvas.getContext('2d');
const placeholder = document.getElementById('videoPlaceholder');
const densityChartCanvas = document.getElementById('densityChartCanvas');
const imageInput = document.getElementById('imageInput');
const videoInput = document.getElementById('videoInput');

const state = {
  polling: null,
  drawingMode: null,
  roiPoints: [],
  calibrationPoints: [],
  densitySeries: [],
  authMode: 'login',
  currentUser: null
};

showLoginBtn.addEventListener('click', () => setAuthMode('login'));
showRegisterBtn.addEventListener('click', () => setAuthMode('register'));
loginForm.addEventListener('submit', handleLogin);
registerForm.addEventListener('submit', handleRegister);
sidebarAuthBtn.addEventListener('click', handleLogout);
profileForm.addEventListener('submit', updateProfile);
passwordForm.addEventListener('submit', updatePassword);
alertEmailForm.addEventListener('submit', updateAlertEmail);

document.getElementById('saveCalibrationBtn').addEventListener('click', saveCalibration);
document.getElementById('startCameraBtn').addEventListener('click', startWebcam);
document.getElementById('clearRoiBtn').addEventListener('click', clearRoi);
imageInput.addEventListener('change', uploadImage);
videoInput.addEventListener('change', uploadVideo);

navItems.forEach((button) => {
  button.addEventListener('click', () => {
    navItems.forEach((item) => item.classList.remove('active'));
    pages.forEach((page) => page.classList.remove('active'));
    button.classList.add('active');
    document.getElementById(button.dataset.page).classList.add('active');
    if (button.dataset.page === 'analytics-page') loadAnalytics();
    if (button.dataset.page === 'alerts-page') loadAlerts();
  });
});

document.getElementById('roiModeBtn').addEventListener('click', () => {
  state.drawingMode = 'roi';
  state.roiPoints = [];
  setRoiStatus('ROI drawing: click 4 points on the feed');
  redrawOverlay();
});

document.getElementById('calibrationModeBtn').addEventListener('click', () => {
  state.drawingMode = 'calibration';
  state.calibrationPoints = [];
  setRoiStatus('Calibration: click 2 points on a known object');
  redrawOverlay();
});

overlayCanvas.addEventListener('click', async (event) => {
  if (!state.drawingMode) return;
  const rect = overlayCanvas.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * overlayCanvas.width;
  const y = ((event.clientY - rect.top) / rect.height) * overlayCanvas.height;

  if (state.drawingMode === 'roi') {
    state.roiPoints.push([Math.round(x), Math.round(y)]);
    if (state.roiPoints.length === 4) {
      await fetch('/api/roi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points: state.roiPoints })
      });
      state.drawingMode = null;
      setRoiStatus('ROI active');
    }
  } else {
    state.calibrationPoints.push([Math.round(x), Math.round(y)]);
    if (state.calibrationPoints.length === 2) {
      state.drawingMode = null;
      setRoiStatus('Calibration points captured. Enter known length and save.');
    }
  }
  redrawOverlay();
});

videoFeed.addEventListener('load', () => {
  fitOverlay();
  placeholder.style.display = 'none';
  videoFeed.style.display = 'block';
  overlayCanvas.style.display = 'block';
});

window.addEventListener('resize', () => {
  fitOverlay();
  redrawOverlay();
});

setAuthMode('login');
bootstrapAuth();

function setAuthMode(mode) {
  state.authMode = mode;
  loginForm.classList.toggle('hidden', mode !== 'login');
  registerForm.classList.toggle('hidden', mode !== 'register');
  showLoginBtn.className = `btn ${mode === 'login' ? 'btn-primary' : 'btn-ghost'} auth-toggle`;
  showRegisterBtn.className = `btn ${mode === 'register' ? 'btn-primary' : 'btn-ghost'} auth-toggle`;
  clearMessage(authMessage);
}

async function bootstrapAuth() {
  const response = await fetch('/api/auth/status');
  const data = await response.json();
  setAuthenticated(Boolean(data.authenticated), data.user || null);
  if (data.authenticated) beginPolling();
}

async function handleLogin(event) {
  event.preventDefault();
  const payload = {
    email: document.getElementById('loginEmail').value.trim(),
    password: document.getElementById('loginPassword').value
  };
  await submitAuth('/api/login', payload);
}

async function handleRegister(event) {
  event.preventDefault();
  const payload = {
    name: document.getElementById('registerName').value.trim(),
    email: document.getElementById('registerEmail').value.trim(),
    password: document.getElementById('registerPassword').value
  };
  await submitAuth('/api/signup', payload);
}

async function submitAuth(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) {
    showMessage(authMessage, data.error || 'Authentication failed.', true);
    return;
  }
  showMessage(authMessage, data.message || 'Success.', false);
  setAuthenticated(Boolean(data.authenticated), data.user || null);
  loginForm.reset();
  registerForm.reset();
  beginPolling();
}

async function handleLogout() {
  const response = await fetch('/api/logout', { method: 'POST' });
  const data = await response.json();
  if (response.ok) {
    stopPolling();
    setAuthenticated(false, null);
    clearViewer();
    showMessage(authMessage, data.message || 'Logged out successfully.', false);
    setAuthMode('login');
  }
}

function setAuthenticated(isAuthenticated, user) {
  state.currentUser = user;
  loginScreen.classList.toggle('hidden', isAuthenticated);
  dashboard.classList.toggle('hidden', !isAuthenticated);
  sidebarAuthBtn.textContent = isAuthenticated ? 'Logout' : 'Login';
  if (user) {
    userChip.textContent = `${user.name} • ${user.email}`;
    document.getElementById('profileNameInput').value = user.name || '';
    document.getElementById('profileEmailInput').value = user.email || '';
    document.getElementById('alertEmailInput').value = user.alert_email || user.email || '';
  } else {
    userChip.textContent = 'Not signed in';
    document.getElementById('profileNameInput').value = '';
    document.getElementById('profileEmailInput').value = '';
    document.getElementById('alertEmailInput').value = '';
  }
}

async function updateProfile(event) {
  event.preventDefault();
  const payload = { name: document.getElementById('profileNameInput').value.trim() };
  const response = await fetch('/api/account/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) {
    showMessage(profileMessage, data.error || 'Profile update failed.', true);
    return;
  }
  setAuthenticated(Boolean(data.authenticated), data.user || null);
  showMessage(profileMessage, data.message || 'Profile updated.', false);
}

async function updatePassword(event) {
  event.preventDefault();
  const payload = {
    current_password: document.getElementById('currentPasswordInput').value,
    new_password: document.getElementById('newPasswordInput').value
  };
  const response = await fetch('/api/account/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) {
    showMessage(passwordMessage, data.error || 'Password update failed.', true);
    return;
  }
  passwordForm.reset();
  showMessage(passwordMessage, data.message || 'Password changed.', false);
}

async function updateAlertEmail(event) {
  event.preventDefault();
  const payload = {
    alert_email: document.getElementById('alertEmailInput').value.trim()
  };
  const response = await fetch('/api/account/alert-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) {
    showMessage(alertEmailMessage, data.error || 'Alert email update failed.', true);
    return;
  }
  setAuthenticated(Boolean(data.authenticated), data.user || null);
  showMessage(alertEmailMessage, data.message || 'Alert email updated.', false);
}

function showMessage(element, message, isError) {
  element.textContent = message;
  element.classList.remove('hidden');
  element.style.color = isError ? '#fecaca' : '#86efac';
}

function clearMessage(element) {
  element.textContent = '';
  element.classList.add('hidden');
}

async function clearRoi() {
  await fetch('/api/roi/clear', { method: 'POST' });
  state.roiPoints = [];
  redrawOverlay();
  setRoiStatus('ROI cleared');
}

async function uploadImage(event) {
  const file = event.target.files[0];
  if (!file) return;
  stopPolling();
  const formData = new FormData();
  formData.append('image', file);
  const response = await fetch('/upload_image', { method: 'POST', body: formData });
  const data = await response.json();
  if (!response.ok || !data.filename) {
    setRoiStatus(data.error || 'Image upload failed');
    return;
  }
  videoFeed.src = `/image_result/${encodeURIComponent(data.filename)}?t=${Date.now()}`;
  updateMetrics(data.status || {});
  setRoiStatus('Image processed');
}

async function uploadVideo(event) {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('video', file);
  const response = await fetch('/upload_video', { method: 'POST', body: formData });
  const data = await response.json();
  if (!response.ok || !data.filename) {
    setRoiStatus(data.error || 'Video upload failed');
    return;
  }
  videoFeed.src = `/video_feed/${encodeURIComponent(data.filename)}`;
  beginPolling();
}

function startWebcam() {
  videoFeed.src = '/webcam_feed';
  beginPolling();
}

function beginPolling() {
  stopPolling();
  state.polling = setInterval(fetchStatus, 1000);
  fetchStatus();
}

function stopPolling() {
  if (state.polling) {
    clearInterval(state.polling);
    state.polling = null;
  }
}

async function fetchStatus() {
  const response = await fetch('/detection_status');
  const data = await response.json();
  updateMetrics(data);
}

function updateMetrics(data) {
  document.getElementById('liveCountMetric').textContent = data.live_count ?? 0;
  document.getElementById('uniqueMetric').textContent = data.unique_people ?? 0;
  document.getElementById('peakMetric').textContent = data.peak_count ?? 0;
  document.getElementById('avgMetric').textContent = formatNumber(data.avg_per_frame ?? 0);
  document.getElementById('fpsMetric').textContent = formatNumber(data.fps ?? 0);
  document.getElementById('calibrationChip').textContent = data.pixel_cm ? `1 px = ${data.pixel_cm.toFixed(2)} cm` : '1 px = -- cm';

  const modelStatus = data.model_status || (data.yolo_ready ? 'YOLOv8 Ready' : 'YOLOv8 person model not loaded');
  const systemStatus = `System Online • ${modelStatus}`;
  document.getElementById('brandStatus').textContent = systemStatus;
  document.getElementById('sidebarStatus').textContent = systemStatus;
  document.getElementById('feedStatus').textContent = systemStatus;

  state.roiPoints = data.roi_points || state.roiPoints;
  state.calibrationPoints = data.calibration_points || state.calibrationPoints;
  redrawOverlay();

  const densityText = data.density_value !== null && data.density_value !== undefined
    ? `${data.density_label} Density (${formatNumber(data.density_value)} p/m2)`
    : `${data.density_label || 'Low'} Density (${data.live_count ?? 0} persons/frame)`;
  const badge = document.getElementById('densityBadge');
  const badgeText = document.getElementById('densityBadgeText');
  badgeText.textContent = densityText;
  badge.style.borderColor = withAlpha(data.density_color || '#22c55e', 0.4);
  badge.style.background = withAlpha(data.density_color || '#22c55e', 0.12);
  badge.querySelector('.dot').style.background = data.density_color || '#22c55e';

  state.densitySeries.push(data.density_value ?? data.live_count ?? 0);
  if (state.densitySeries.length > 30) state.densitySeries.shift();
  drawLineChart(densityChartCanvas, state.densitySeries, '#14b8a6', 'Density (p/m2)', 'rgba(20, 184, 166, 0.16)');

  const alertBar = document.getElementById('alertBar');
  if (data.alert && data.alert.active) {
    alertBar.textContent = `WARNING ${data.alert.message}`;
    alertBar.classList.remove('hidden');
  } else {
    alertBar.classList.add('hidden');
  }
}

async function saveCalibration() {
  const realLength = parseFloat(document.getElementById('realLengthInput').value);
  if (!realLength || state.calibrationPoints.length !== 2) {
    setRoiStatus('Select 2 calibration points and enter a known length');
    return;
  }
  const response = await fetch('/api/calibration', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ points: state.calibrationPoints, real_length_m: realLength })
  });
  const data = await response.json();
  setRoiStatus(data.pixel_cm ? `Calibration saved: 1 px = ${data.pixel_cm.toFixed(2)} cm` : 'Calibration saved');
  fetchStatus();
}

async function loadAnalytics() {
  const response = await fetch('/api/analytics');
  const data = await response.json();
  drawLineChart(document.getElementById('analyticsDensityCanvas'), data.densitySeries.map((entry) => entry.value), '#f59e0b', 'Density (p/m2)', 'rgba(245, 158, 11, 0.16)');
  drawBarChart(document.getElementById('analyticsUniqueCanvas'), data.uniqueSeries.map((entry) => entry.value), '#3b82f6');
  renderHeatmap(data.alertHeatmap || []);
}

async function loadAlerts() {
  const response = await fetch('/api/alerts');
  const data = await response.json();
  const tbody = document.getElementById('alertsTableBody');
  tbody.innerHTML = '';
  (data.alerts || []).forEach((alert) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${alert.timestamp}</td><td>${alert.duration}s</td><td>${formatNumber(alert.peak_density)}</td><td>${alert.status}</td>`;
    tbody.appendChild(row);
  });
}

function clearViewer() {
  videoFeed.removeAttribute('src');
  videoFeed.style.display = 'none';
  overlayCanvas.style.display = 'none';
  placeholder.style.display = 'grid';
  state.roiPoints = [];
  state.calibrationPoints = [];
  redrawOverlay();
}

function fitOverlay() {
  overlayCanvas.width = videoFeed.clientWidth || overlayCanvas.parentElement.clientWidth;
  overlayCanvas.height = videoFeed.clientHeight || overlayCanvas.parentElement.clientHeight;
}

function redrawOverlay() {
  overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  if (state.roiPoints.length) {
    overlayCtx.setLineDash([8, 6]);
    overlayCtx.strokeStyle = '#2dd4bf';
    overlayCtx.lineWidth = 2;
    overlayCtx.beginPath();
    state.roiPoints.forEach((point, index) => {
      if (index === 0) overlayCtx.moveTo(point[0], point[1]);
      else overlayCtx.lineTo(point[0], point[1]);
    });
    if (state.roiPoints.length === 4) overlayCtx.closePath();
    overlayCtx.stroke();
    overlayCtx.setLineDash([]);
  }
  if (state.calibrationPoints.length) {
    overlayCtx.strokeStyle = '#60a5fa';
    overlayCtx.lineWidth = 2;
    overlayCtx.beginPath();
    overlayCtx.moveTo(state.calibrationPoints[0][0], state.calibrationPoints[0][1]);
    if (state.calibrationPoints[1]) overlayCtx.lineTo(state.calibrationPoints[1][0], state.calibrationPoints[1][1]);
    overlayCtx.stroke();
  }
}

function renderHeatmap(entries) {
  const grid = document.getElementById('heatmapGrid');
  grid.innerHTML = '';
  entries.forEach((entry) => {
    const cell = document.createElement('div');
    cell.className = 'heatmap-cell';
    cell.style.background = `rgba(239, 68, 68, ${0.12 + entry.count * 0.14})`;
    cell.innerHTML = `<strong>${String(entry.hour).padStart(2, '0')}:00</strong><p>${entry.count} alerts</p>`;
    grid.appendChild(cell);
  });
}

function drawLineChart(canvas, values, color, label, fillColor = 'rgba(45, 212, 191, 0.12)') {
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  drawAxes(ctx, width, height, label);
  if (!values.length) return;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const points = values.map((value, index) => ({
    x: 40 + (index / Math.max(values.length - 1, 1)) * (width - 60),
    y: height - 30 - ((value - min) / Math.max(max - min, 1)) * (height - 70)
  }));

  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach((point) => ctx.lineTo(point.x, point.y));
  ctx.lineTo(points[points.length - 1].x, height - 30);
  ctx.lineTo(points[0].x, height - 30);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();

  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  points.slice(1).forEach((point) => ctx.lineTo(point.x, point.y));
  ctx.stroke();
}

function drawBarChart(canvas, values, color) {
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  ctx.clearRect(0, 0, width, height);
  drawAxes(ctx, width, height, 'Unique People');
  const max = Math.max(...values, 1);
  values.forEach((value, index) => {
    const barWidth = (width - 60) / Math.max(values.length, 1) - 8;
    const x = 42 + index * ((width - 60) / Math.max(values.length, 1));
    const barHeight = (value / max) * (height - 70);
    ctx.fillStyle = color;
    ctx.fillRect(x, height - 30 - barHeight, barWidth, barHeight);
  });
}

function drawAxes(ctx, width, height, label) {
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.3)';
  ctx.beginPath();
  ctx.moveTo(40, 18);
  ctx.lineTo(40, height - 30);
  ctx.lineTo(width - 20, height - 30);
  ctx.stroke();
  ctx.fillStyle = '#90a4b8';
  ctx.fillText(label, 18, 16);
}

function setRoiStatus(text) {
  document.getElementById('roiStatus').textContent = text;
}

function formatNumber(value) {
  return Number(value || 0).toFixed(2);
}

function withAlpha(hex, alpha) {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
