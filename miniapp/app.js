const authView = document.getElementById("authView");
const dashboardView = document.getElementById("dashboardView");

const authForm = document.getElementById("authForm");
const switchMode = document.getElementById("switchMode");

const authTitle = document.getElementById("authTitle");
const authText = document.getElementById("authText");
const authButton = document.getElementById("authButton");

const confirmWrap = document.getElementById("confirmWrap");
const username = document.getElementById("username");
const tgUser = document.getElementById("tgUser");

let loginMode = false;


/* =========================
   TELEGRAM MINI APP
========================= */

const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();

    const telegramUser = tg.initDataUnsafe?.user;

    if (telegramUser) {

        const handle = telegramUser.username
            ? `@${telegramUser.username}`
            : (telegramUser.first_name || "Telegram user");

        tgUser.textContent = handle;

        /*
         * Username available:
         * Auto-fill it during registration.
         *
         * NOTE:
         * initDataUnsafe is used ONLY for UI display here.
         * Backend authentication must verify tg.initData
         * server-side in the next step.
         */
        if (telegramUser.username) {
            username.value = telegramUser.username;
        }

        const firstName = telegramUser.first_name || "User";

        document.getElementById("dashName").textContent = firstName;

        document.getElementById("dashAvatar").textContent =
            firstName.charAt(0).toUpperCase();
    }
}


/* =========================
   REGISTER / LOGIN SWITCH
========================= */

switchMode.addEventListener("click", () => {

    loginMode = !loginMode;

    if (loginMode) {

        /* LOGIN MODE */

        authTitle.textContent = "Welcome back";

        authText.textContent =
            "Login to open your personal dashboard.";

        authButton.innerHTML =
            'LOGIN <span>→</span>';

        confirmWrap.classList.add("hidden");

        document.getElementById("usernameLabel").textContent =
            "Username";

        username.placeholder =
            "Enter your username";

        username.value = "";

        document.getElementById("password").value = "";

        document.getElementById("confirmPassword").value = "";

        switchMode.innerHTML =
            'New here? <b>Create account</b>';

    } else {

        /* REGISTER MODE */

        authTitle.textContent =
            "Create your account";

        authText.textContent =
            "Register once and use your personal dashboard every time.";

        authButton.innerHTML =
            'CREATE ACCOUNT <span>→</span>';

        confirmWrap.classList.remove("hidden");

        document.getElementById("usernameLabel").textContent =
            "Username";

        username.placeholder =
            "Choose a username";

        username.value = "";

        document.getElementById("password").value = "";

        document.getElementById("confirmPassword").value = "";

        switchMode.innerHTML =
            'Already have an account? <b>Login</b>';
    }
});


/* =========================
   AUTH FORM
========================= */

authForm.addEventListener("submit", (e) => {

    e.preventDefault();

    const password =
        document.getElementById("password").value;

    const confirmPassword =
        document.getElementById("confirmPassword").value;


    /* =====================
       REGISTER VALIDATION
    ===================== */

    if (!loginMode) {

        if (!username.value.trim()) {
            alert("Please enter a username.");
            return;
        }

        if (!password) {
            alert("Please enter a password.");
            return;
        }

        if (password.length < 6) {
            alert("Password must be at least 6 characters.");
            return;
        }

        if (password !== confirmPassword) {
            alert("Passwords do not match.");
            return;
        }
    }


    /* =====================
       LOGIN VALIDATION
    ===================== */

    if (loginMode) {

        if (!username.value.trim()) {
            alert("Please enter your username.");
            return;
        }

        if (!password) {
            alert("Please enter your password.");
            return;
        }
    }


    /*
     * STEP 1 ONLY
     *
     * At this stage we only show the dashboard shell.
     *
     * Real registration/login will be connected to the
     * secure Flask backend in Step 2.
     */

    authView.classList.add("hidden");

    dashboardView.classList.remove("hidden");


    /* =====================
       DASHBOARD USER INFO
    ===================== */

    const displayName =
        username.value.trim() || "User";

    document.getElementById("dashName").textContent =
        displayName;

    document.getElementById("dashAvatar").textContent =
        displayName.charAt(0).toUpperCase();
});


/* =========================
   QUICK ACCESS BUTTONS
========================= */

document.querySelectorAll(".feature").forEach((button) => {

    button.addEventListener("click", () => {

        const target =
            button.dataset.target;

        if (!target) {
            return;
        }

        /*
         * Dashboard sections will be connected
         * in the upcoming steps.
         */

        console.log("Opening:", target);

    });

});


/* =========================
   BOTTOM NAVIGATION
========================= */

document.querySelectorAll(".bottom-nav button").forEach((button) => {

    button.addEventListener("click", () => {

        document.querySelectorAll(".bottom-nav button")
            .forEach((item) => {
                item.classList.remove("active");
            });

        button.classList.add("active");

        const target =
            button.dataset.target;

        if (!target) {
            return;
        }

        console.log("Navigation:", target);

    });

});


/* =========================
   TELEGRAM THEME SUPPORT
========================= */

if (tg) {

    /*
     * Use Telegram's theme colors when available.
     */

    const theme = tg.themeParams || {};

    if (theme.bg_color) {
        document.body.style.background =
            theme.bg_color;
    }

    if (theme.text_color) {
        document.body.style.color =
            theme.text_color;
    }
}


/* =========================
   MINI APP STARTUP
========================= */

console.log("Saksham Mini App loaded successfully.");
