class WiFiSetup {
    constructor() {
        this.statusCard = document.getElementById('status-card');
        this.statusInfo = document.getElementById('status-info');
        this.ssidInput = document.getElementById('ssid-input');
        this.passwordInput = document.getElementById('password-input');
        this.connectBtn = document.getElementById('connect-btn');
        // this.completeBtn = document.getElementById('complete-btn'); // Commented out
        this.alertContainer = document.getElementById('alert-container');
        
        this.init();
    }
    
    init() {
        this.connectBtn.addEventListener('click', () => this.connectToNetwork());
        // this.completeBtn.addEventListener('click', () => this.completeSetup()); // Commented out
        
        // Remove automatic status checking since we'll redirect to status page
        // this.checkStatus();
        // setInterval(() => this.checkStatus(), 5000);
        
        // Show initial disconnected state
        this.updateStatusDisplay({ connected: false });
    }
    
    // Keep this method but don't use it automatically
    async checkStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();
            this.updateStatusDisplay(status);
        } catch (error) {
            console.error('Status check failed:', error);
        }
    }
    
    updateStatusDisplay(status) {
        if (status.connected) {
            this.statusCard.className = 'status-card';
            this.statusInfo.innerHTML = `
                <strong>Connected to:</strong> ${status.ssid}<br>
                <strong>IP Address:</strong> ${status.ip_address || 'N/A'}<br>
                <strong>Interface:</strong> ${status.interface || 'N/A'}
            `;
            // this.completeBtn.style.display = 'inline-block'; // Commented out
        } else {
            this.statusCard.className = 'status-card disconnected';
            this.statusInfo.textContent = 'Ready to connect to WiFi network';
            // this.completeBtn.style.display = 'none'; // Commented out
        }
    }
    
    async connectToNetwork() {
        const ssid = this.ssidInput.value.trim();
        const password = this.passwordInput.value;
        
        if (!ssid) {
            this.showAlert('Please enter a network name', 'error');
            return;
        }
        
        this.connectBtn.textContent = 'Connecting...';
        this.connectBtn.disabled = true;
        
        const passwordInfo = password ? 'with password' : '(open network)';
        
        try {
            // Fire the request to the backend. We don't need to wait for the response
            // because the server will disconnect.
            fetch('/api/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ssid: ssid, password: password })
            });

            // Show connection progress with animated messages
            this.showConnectionProgress(ssid, async () => {
                const currentPort = window.location.port || '8080';
                
                // Try to get the device's mDNS hostname from the backend
                let redirectHostname = 'localhost'; // Fallback
                
                try {
                    // Make a quick request to get the device's mDNS hostname
                    const hostnameResponse = await fetch('/api/status');
                    const statusData = await hostnameResponse.json();
                    if (statusData.mdns_hostname) {
                        redirectHostname = statusData.mdns_hostname.endsWith('.local') 
                            ? statusData.mdns_hostname 
                            : `${statusData.mdns_hostname}.local`;
                    }
                } catch (error) {
                    // If we can't get the hostname from the API, try to construct it
                    const currentHostname = window.location.hostname;
                    if (currentHostname === '192.168.4.1') {
                        // We're on hotspot - we'll redirect and let the browser keep trying
                        // until the device connects and mDNS starts working
                        redirectHostname = 'localhost'; // Generic fallback
                    } else {
                        redirectHostname = currentHostname.endsWith('.local') 
                            ? currentHostname 
                            : `${currentHostname}.local`;
                    }
                }
                
                const redirectUrl = `http://${redirectHostname}:${currentPort}/wifi_status`;
                window.location.href = redirectUrl;
            });
            
        } catch (error) {
            // This catch block is unlikely to be hit because we don't await the fetch,
            // but it's good practice to keep it.
            console.error('Error sending connect request:', error);
            this.showAlert('Failed to send connect request.', 'error');
            this.connectBtn.textContent = 'Connect';
            this.connectBtn.disabled = false;
        }
    }
    
    showConnectionProgress(ssid, onComplete) {
        const steps = [
            { message: `Initiating connection to ${ssid}...`, duration: 1000 },
            { message: 'Stopping WiFi hotspot...', duration: 1000 },
            { message: 'Connecting to network...', duration: 1500 },
            { message: 'Establishing network connection...', duration: 1000 },
            { message: 'Starting mDNS service...', duration: 500 },
            { message: 'Redirecting to device status page...', duration: 100 }
        ];
        
        let currentStep = 0;
        let spinnerInterval;
        
        const showStep = () => {
            if (currentStep < steps.length) {
                const step = steps[currentStep];
                
                // Start animating spinner for this step
                const updateSpinner = () => {
                    const spinner = this.getSpinner();
                    this.showAlert(`${spinner} ${step.message}`, 'info');
                };
                
                // Show initial message
                updateSpinner();
                
                // Update spinner every 100ms for animation
                spinnerInterval = setInterval(updateSpinner, 100);
                
                // Move to next step after duration
                setTimeout(() => {
                    clearInterval(spinnerInterval);
                    currentStep++;
                    showStep();
                }, step.duration);
            } else {
                // All steps shown, execute completion callback
                onComplete();
            }
        };
        
        showStep();
    }
    
    getSpinner() {
        // Simple CSS spinner using Unicode characters
        const frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
        const frameIndex = Math.floor(Date.now() / 100) % frames.length;
        return `<span style="color: #007bff; font-weight: bold;">${frames[frameIndex]}</span>`;
    }
    
    // Commented out complete setup functionality
    /*
    async completeSetup() {
        try {
            const response = await fetch('/api/complete-setup', {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.success) {
                this.showAlert('Setup completed successfully!', 'success');
            }
        } catch (error) {
            console.error('Complete setup failed:', error);
        }
    }
    */
    
    showAlert(message, type) {
        const alertClass = `alert-${type}`;
        const alertHtml = `
            <div class="alert ${alertClass}">
                ${message}
            </div>
        `;
        
        this.alertContainer.innerHTML = alertHtml;
        
        setTimeout(() => {
            this.alertContainer.innerHTML = '';
        }, 5000);
    }
}

// Initialize the WiFi setup interface when the page loads
document.addEventListener('DOMContentLoaded', function() {
    window.wifiSetup = new WiFiSetup();
}); 
