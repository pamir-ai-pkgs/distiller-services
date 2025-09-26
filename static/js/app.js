// Distiller WiFi Setup - Main JavaScript

// Global WebSocket connection
let globalWs = null;
let reconnectTimer = null;

// Initialize WebSocket connection
function initWebSocket() {
  if (globalWs && globalWs.readyState === WebSocket.OPEN) {
    return;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  globalWs = new WebSocket(wsUrl);

  globalWs.onopen = function () {
    clearTimeout(reconnectTimer);
  };

  globalWs.onmessage = function (event) {
    try {
      const data = JSON.parse(event.data);
      handleGlobalStatusUpdate(data);
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };

  globalWs.onerror = function (error) {
    console.error('WebSocket error:', error);
  };

  globalWs.onclose = function () {
    globalWs = null;

    // Attempt reconnection after 3 seconds
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(initWebSocket, 3000);
  };

  // Send periodic ping to keep connection alive
  setInterval(() => {
    if (globalWs && globalWs.readyState === WebSocket.OPEN) {
      globalWs.send('ping');
    }
  }, 30000);
}

// Handle global status updates
function handleGlobalStatusUpdate(data) {
  const statusElement = document.getElementById('connection-status');
  if (statusElement) {
    let statusText = 'UNKNOWN';
    switch (data.state) {
      case 'AP_MODE':
        statusText = 'SETUP MODE';
        break;
      case 'CONNECTING':
        statusText = 'CONNECTING';
        break;
      case 'CONNECTED':
        statusText = 'CONNECTED';
        break;
      case 'FAILED':
        statusText = 'FAILED';
        break;
      case 'DISCONNECTED':
        statusText = 'DISCONNECTED';
        break;
    }
    statusElement.textContent = `[ ${statusText} ]`;
  }
}

// Session ID management
function getSessionId() {
  let sessionId = localStorage.getItem('distiller_session_id');
  if (!sessionId) {
    sessionId = generateUUID();
    localStorage.setItem('distiller_session_id', sessionId);
  }
  return sessionId;
}

// Generate UUID v4
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// Prevent form resubmission on page refresh
if (window.history.replaceState) {
  window.history.replaceState(null, null, window.location.href);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
  // Initialize WebSocket
  initWebSocket();

  // Set session ID cookie if not present
  const sessionId = getSessionId();
  if (!document.cookie.includes('session_id')) {
    document.cookie = `session_id=${sessionId}; max-age=3600; path=/`;
  }

  // Add keyboard shortcuts
  document.addEventListener('keydown', function (e) {
    // Ctrl+R or F5 to refresh network list
    if ((e.ctrlKey && e.key === 'r') || e.key === 'F5') {
      e.preventDefault();
      if (typeof refreshNetworks === 'function') {
        refreshNetworks();
      } else {
        location.reload();
      }
    }
  });

  // Add visibility change handler to reconnect WebSocket when page becomes visible
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) {
      initWebSocket();
    }
  });
});

// Clean up on page unload
window.addEventListener('beforeunload', function () {
  if (globalWs) {
    globalWs.close();
  }
  clearTimeout(reconnectTimer);
});
