/**
 * Common JavaScript functionality for Distiller CM5 WiFi Setup Interface
 * Provides shared utilities and functions across all pages
 */

class CommonUtils {
  /**
   * Show a temporary notification message
   * @param {string} message - The message to display
   * @param {string} type - Type of notification: 'success', 'error', 'info', 'warning'
   * @param {number} duration - Duration in milliseconds (default: 5000)
   */
  static showNotification(message, type = "info", duration = 5000) {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll(".notification");
    existingNotifications.forEach((n) => n.remove());

    // Create notification element
    const notification = document.createElement("div");
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
      <div class="notification-content">
        ${message}
        <button class="notification-close" onclick="this.parentElement.parentElement.remove()">[×]</button>
      </div>
    `;

    // Add styles if not already added
    if (!document.getElementById("notification-styles")) {
      const styles = document.createElement("style");
      styles.id = "notification-styles";
      styles.innerHTML = `
        .notification {
          position: fixed;
          top: 20px;
          right: 20px;
          max-width: 400px;
          background: #ffffff;
          border: 2px solid #000000;
          padding: 15px;
          font-family: "MartianMono", monospace;
          font-size: 12px;
          z-index: 1000;
          animation: slideIn 0.3s ease;
        }
        .notification-success { border-color: #28a745; }
        .notification-error { border-color: #dc3545; }
        .notification-warning { border-color: #ffc107; }
        .notification-info { border-color: #007bff; }
        .notification-content {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 10px;
        }
        .notification-close {
          background: none;
          border: none;
          font-family: "MartianMono", monospace;
          font-size: 12px;
          cursor: pointer;
          padding: 0;
          margin-left: 10px;
          flex-shrink: 0;
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
        @media (max-width: 600px) {
          .notification {
            top: 10px;
            right: 10px;
            left: 10px;
            max-width: none;
          }
        }
      `;
      document.head.appendChild(styles);
    }

    // Add to page
    document.body.appendChild(notification);

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        if (notification.parentElement) {
          notification.remove();
        }
      }, duration);
    }
  }

  /**
   * Make an API request with proper error handling
   * @param {string} url - API endpoint
   * @param {Object} options - Fetch options
   * @returns {Promise<Object>} - Response data
   */
  static async apiRequest(url, options = {}) {
    try {
      const response = await fetch(url, {
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${url}`, error);
      throw error;
    }
  }

  /**
   * Format device information for display
   * @param {Object} info - Device info object
   * @returns {string} - Formatted string
   */
  static formatDeviceInfo(info) {
    const parts = [];
    if (info.ssid) parts.push(`Network: ${info.ssid}`);
    if (info.ip_address) parts.push(`IP: ${info.ip_address}`);
    if (info.interface) parts.push(`Interface: ${info.interface}`);
    return parts.join(" • ");
  }

  /**
   * Show loading state on an element
   * @param {HTMLElement} element - Element to show loading on
   * @param {string} loadingText - Text to display while loading
   */
  static showLoading(element, loadingText = "Loading...") {
    element.dataset.originalText = element.textContent;
    element.textContent = loadingText;
    element.disabled = true;
    element.classList.add("loading");
  }

  /**
   * Hide loading state on an element
   * @param {HTMLElement} element - Element to hide loading from
   */
  static hideLoading(element) {
    if (element.dataset.originalText) {
      element.textContent = element.dataset.originalText;
      delete element.dataset.originalText;
    }
    element.disabled = false;
    element.classList.remove("loading");
  }

  /**
   * Validate SSID format
   * @param {string} ssid - Network SSID to validate
   * @returns {Object} - Validation result with isValid and message
   */
  static validateSSID(ssid) {
    if (!ssid || ssid.trim().length === 0) {
      return { isValid: false, message: "Network name is required" };
    }

    if (ssid.length > 32) {
      return {
        isValid: false,
        message: "Network name must be 32 characters or less",
      };
    }

    // Check for invalid characters (basic check)
    if (ssid.includes("\0")) {
      return {
        isValid: false,
        message: "Network name contains invalid characters",
      };
    }

    return { isValid: true, message: "" };
  }

  /**
   * Add event listeners when DOM is ready
   * @param {Function} callback - Function to call when DOM is ready
   */
  static onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  /**
   * Throttle function execution
   * @param {Function} func - Function to throttle
   * @param {number} limit - Time limit in milliseconds
   * @returns {Function} - Throttled function
   */
  static throttle(func, limit) {
    let inThrottle;
    return function () {
      const args = arguments;
      const context = this;
      if (!inThrottle) {
        func.apply(context, args);
        inThrottle = true;
        setTimeout(() => (inThrottle = false), limit);
      }
    };
  }

  /**
   * Debounce function execution
   * @param {Function} func - Function to debounce
   * @param {number} delay - Delay in milliseconds
   * @returns {Function} - Debounced function
   */
  static debounce(func, delay) {
    let timeoutId;
    return function () {
      const args = arguments;
      const context = this;
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => func.apply(context, args), delay);
    };
  }
}

// Make CommonUtils available globally
window.CommonUtils = CommonUtils;
