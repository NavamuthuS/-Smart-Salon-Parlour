document.addEventListener("DOMContentLoaded", function () {
  // -------------------------------------------------------------
  // Dark / Light theme toggle (preference saved in the browser)
  // -------------------------------------------------------------
  var themeBtn = document.getElementById("themeToggleBtn");
  var savedTheme = localStorage.getItem("salon-theme") || "light";
  if (savedTheme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
    if (themeBtn) themeBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        localStorage.setItem("salon-theme", "light");
        themeBtn.innerHTML = '<i class="fa-solid fa-moon"></i>';
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
        localStorage.setItem("salon-theme", "dark");
        themeBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
      }
    });
  }

  // -------------------------------------------------------------
  // Loading spinner: show while a form submits or a link navigates
  // -------------------------------------------------------------
  var overlay = document.getElementById("loadingOverlay");
  var showSpinner = function () {
    if (overlay) overlay.classList.add("active");
  };
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      // Only show spinner if the form will actually submit (validation passes)
      setTimeout(showSpinner, 0);
    });
  });
  document.querySelectorAll('a[href]:not([href^="#"]):not([target="_blank"])').forEach(function (link) {
    link.addEventListener("click", function () {
      showSpinner();
    });
  });

  // Prevent selecting a past date on the booking form
  var dateInput = document.querySelector('input[name="date"]');
  if (dateInput) {
    var today = new Date().toISOString().split("T")[0];
    dateInput.setAttribute("min", today);
  }

  // Auto-dismiss alerts after 4 seconds
  var alerts = document.querySelectorAll(".alert");
  alerts.forEach(function (alert) {
    setTimeout(function () {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    }, 4000);
  });

  // Require at least one service checkbox on booking form
  var bookingForm = document.querySelector(".booking-form");
  if (bookingForm) {
    bookingForm.addEventListener("submit", function (e) {
      var checked = bookingForm.querySelectorAll('input[name="services"]:checked');
      if (checked.length === 0) {
        e.preventDefault();
        alert("Please select at least one service before confirming your booking.");
      }
    });
  }

  // -------------------------------------------------------------
  // Live price calculator on the booking page
  // -------------------------------------------------------------
  var priceCheckboxes = document.querySelectorAll(".price-checkbox");
  var totalDisplay = document.getElementById("totalPriceDisplay");
  if (priceCheckboxes.length && totalDisplay) {
    var updateTotal = function () {
      var total = 0;
      priceCheckboxes.forEach(function (cb) {
        if (cb.checked) total += parseFloat(cb.dataset.price || 0);
      });
      totalDisplay.textContent = "₹" + total;
    };
    priceCheckboxes.forEach(function (cb) {
      cb.addEventListener("change", updateTotal);
    });
    updateTotal();
  }

  // -------------------------------------------------------------
  // EmailJS: notify the chosen staff member right after a booking
  // is confirmed. `window.LAST_BOOKING` is injected by
  // customer_dashboard.html only right after a successful booking.
  // -------------------------------------------------------------
  if (window.LAST_BOOKING && typeof emailjs !== "undefined") {
    var b = window.LAST_BOOKING;

    emailjs.init({ publicKey: EMAILJS_PUBLIC_KEY });

    emailjs
      .send(EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, {
        staff_name: b.staff_name,
        staff_email: b.staff_email,
        customer_name: b.customer_name,
        services: b.services,
        date: b.date,
        time: b.time,
        seat: b.seat,
      })
      .then(function () {
        console.log("Booking email sent to " + b.staff_email);
      })
      .catch(function (err) {
        console.error("EmailJS failed:", err);
      });
  }
});