class WiFiSetup {
  constructor() {
    this.statusCard = document.getElementById("status-card");
    this.statusInfo = document.getElementById("status-info");
    this.ssidInput = document.getElementById("ssid-input");
    this.passwordInput = document.getElementById("password-input");
    this.connectBtn = document.getElementById("connect-btn");
    this.alertContainer = document.getElementById("alert-container");

    this.init();
  }

  init() {
    this.connectBtn.addEventListener("click", () => this.connectToNetwork());
    
    // Show initial disconnected state
    this.updateStatusDisplay({ connected: false });
  }

  // Keep status checking method for manual use
  async checkStatus() {
    try {
      const response = await fetch("/api/status");
      const status = await response.json();
      this.updateStatusDisplay(status);
    } catch (error) {
      console.error("Status check failed:", error);
    }
  }

  updateStatusDisplay(status) {
    if (status.connected) {
      this.statusCard.className = "status-card";
      this.statusInfo.innerHTML = `
                <strong>Connected to:</strong> ${status.ssid}<br>
                <strong>IP Address:</strong> ${status.ip_address || "N/A"}<br>
                <strong>Interface:</strong> ${status.interface || "N/A"}
            `;
    } else {
      this.statusCard.className = "status-card disconnected";
      this.statusInfo.textContent = "Ready to connect to WiFi network";
    }
  }

  async connectToNetwork() {
    const ssid = this.ssidInput.value.trim();
    const password = this.passwordInput.value;

    if (!ssid) {
      this.showAlert("Please enter a network name", "error");
      return;
    }

    this.connectBtn.textContent = "Connecting...";
    this.connectBtn.disabled = true;

    try {
      // Initiate the connection
      const connectResponse = await fetch("/api/connect", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ssid: ssid, password: password }),
      });

      if (!connectResponse.ok) {
        throw new Error("Failed to initiate connection");
      }

      // Show connection status information instead of redirecting
      this.showConnectionStatus(ssid);
      
    } catch (error) {
      console.error("Connection process failed:", error);
      this.showAlert(`Connection failed: ${error.message}`, "error");
      this.connectBtn.textContent = "Connect";
      this.connectBtn.disabled = false;
    }
  }

  showConnectionStatus(ssid) {
    // Show informative message about the connection process
    this.showAlert(`
      <strong>Connection initiated to ${ssid}</strong><br><br>
      The device is now connecting to your WiFi network. This process may take a few moments.<br><br>
      <strong>What happens next:</strong><br>
      • The device will connect to your network<br>
      • You can check the connection status at any time<br>
      • If successful, access your device using its new IP address<br><br>
      <strong>To check status:</strong> Visit the <a href="/status" style="color: #000; text-decoration: underline;">Status Page</a>
    `, "info");
    
    // Reset button after showing the message
    setTimeout(() => {
      this.connectBtn.textContent = "Connect";
      this.connectBtn.disabled = false;
    }, 2000);
  }

  showAlert(message, type) {
    const alertClass = `alert-${type}`;
    const alertHtml = `
            <div class="alert ${alertClass}">
                ${message}
            </div>
        `;

    this.alertContainer.innerHTML = alertHtml;

    // Keep info alerts visible longer, others shorter
    const timeout = type === "info" ? 15000 : 5000;
    setTimeout(() => {
      this.alertContainer.innerHTML = "";
    }, timeout);
  }
}

// Initialize the WiFi setup interface when the page loads
document.addEventListener("DOMContentLoaded", function () {
  window.wifiSetup = new WiFiSetup();
});
