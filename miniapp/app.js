/* =========================================================
   SAKSHAM VIBES — TELEGRAM MINI APP
   Authentication + Dashboard + Wallet + Shop + Rewards
   ========================================================= */

"use strict";

const tg = window.Telegram?.WebApp;

const state = {
    user: null,
    account: null,
    dashboard: null,
    shop: [],
    referral: null,
    membership: null,
    activity: null,
    loggedIn: false
};


/* =========================================================
   TELEGRAM INITIALIZATION
   ========================================================= */

function initTelegram() {
    if (!tg) {
        console.warn("Telegram WebApp SDK not found.");
        return;
    }

    try {
        tg.ready();
        tg.expand();

        if (tg.setHeaderColor) {
            tg.setHeaderColor("#0b0b12");
        }

        if (tg.setBackgroundColor) {
            tg.setBackgroundColor("#08080d");
        }

        if (tg.enableClosingConfirmation) {
            tg.enableClosingConfirmation();
        }
    } catch (error) {
        console.error("Telegram init error:", error);
    }
}


/* =========================================================
   HELPERS
   ========================================================= */

function getTelegramUser() {
    try {
        return tg?.initDataUnsafe?.user || null;
    } catch {
        return null;
    }
}


function getInitData() {
    return tg?.initData || "";
}


async function api(url, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
    };

    const initData = getInitData();

    if (initData) {
        headers["X-Telegram-Init-Data"] = initData;
    }

    const response = await fetch(url, {
        ...options,
        headers,
        credentials: "include"
    });

    let data;

    try {
        data = await response.json();
    } catch {
        throw new Error(`Server returned ${response.status}`);
    }

    if (!response.ok) {
        throw new Error(
            data?.error ||
            data?.message ||
            `Request failed (${response.status})`
        );
    }

    return data;
}


function showToast(message, type = "info") {
    const old = document.querySelector(".sv-toast");

    if (old) {
        old.remove();
    }

    const toast = document.createElement("div");
    toast.className = `sv-toast ${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add("show");
    });

    setTimeout(() => {
        toast.classList.remove("show");

        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 2800);
}


function showLoading(text = "Please wait...") {
    let loader = document.getElementById("sv-loader");

    if (!loader) {
        loader = document.createElement("div");
        loader.id = "sv-loader";
        loader.innerHTML = `
            <div class="sv-loader-box">
                <div class="sv-spinner"></div>
                <div class="sv-loader-text"></div>
            </div>
        `;

        document.body.appendChild(loader);
    }

    loader.querySelector(".sv-loader-text").textContent = text;
    loader.classList.add("show");
}


function hideLoading() {
    const loader = document.getElementById("sv-loader");

    if (loader) {
        loader.classList.remove("show");
    }
}


function escapeHTML(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function getElement(...ids) {
    for (const id of ids) {
        const el = document.getElementById(id);

        if (el) {
            return el;
        }
    }

    return null;
}


/* =========================================================
   USER UI AUTOFILL
   ========================================================= */

function fillTelegramUser() {
    state.user = getTelegramUser();

    if (!state.user) {
        return;
    }

    const usernameInput = getElement(
        "register-username",
        "username",
        "regUsername"
    );

    const telegramUsername = state.user.username
        ? state.user.username
        : "";

    if (usernameInput && telegramUsername) {
        usernameInput.value = telegramUsername;
    }

    const nameElements = document.querySelectorAll(
        "[data-telegram-name]"
    );

    nameElements.forEach((element) => {
        element.textContent =
            state.user.first_name ||
            state.user.username ||
            "User";
    });

    const avatarElements = document.querySelectorAll(
        "[data-telegram-avatar]"
    );

    avatarElements.forEach((element) => {
        if (state.user.photo_url) {
            element.src = state.user.photo_url;
        }
    });
}


/* =========================================================
   PAGE / SECTION HANDLING
   ========================================================= */

function showSection(sectionId) {
    const sections = document.querySelectorAll(
        ".app-section, .page, [data-section]"
    );

    sections.forEach((section) => {
        section.classList.remove("active");
        section.style.display = "";
    });

    const target = document.getElementById(sectionId);

    if (target) {
        target.classList.add("active");
        target.style.display = "";
    }

    const navItems = document.querySelectorAll(
        "[data-nav], .bottom-nav button, .nav-item"
    );

    navItems.forEach((item) => {
        const targetName =
            item.dataset.nav ||
            item.dataset.target ||
            "";

        item.classList.toggle(
            "active",
            targetName === sectionId
        );
    });
}


function setupNavigation() {
    document.addEventListener("click", (event) => {
        const button = event.target.closest(
            "[data-nav], [data-section-target], .nav-item"
        );

        if (!button) {
            return;
        }

        const target =
            button.dataset.nav ||
            button.dataset.sectionTarget ||
            button.dataset.target;

        if (!target) {
            return;
        }

        event.preventDefault();

        showSection(target);

        if (target === "dashboard") {
            loadDashboard();
        }

        if (target === "shop") {
            loadShop();
        }

        if (target === "rewards") {
            loadRewards();
        }

        if (target === "referral") {
            loadReferral();
        }

        if (target === "membership") {
            loadMembership();
        }

        if (target === "activity") {
            loadActivity();
        }
    });
}


/* =========================================================
   AUTH SCREEN
   ========================================================= */

function showAuthScreen() {
    const auth = getElement(
        "auth-screen",
        "auth",
        "login-screen"
    );

    const app = getElement(
        "app-screen",
        "main-app",
        "dashboard-app"
    );

    if (auth) {
        auth.style.display = "";
        auth.classList.add("active");
    }

    if (app) {
        app.style.display = "none";
        app.classList.remove("active");
    }
}


function showAppScreen() {
    const auth = getElement(
        "auth-screen",
        "auth",
        "login-screen"
    );

    const app = getElement(
        "app-screen",
        "main-app",
        "dashboard-app"
    );

    if (auth) {
        auth.style.display = "none";
        auth.classList.remove("active");
    }

    if (app) {
        app.style.display = "";
        app.classList.add("active");
    }

    state.loggedIn = true;

    showSection("dashboard");
}


/* =========================================================
   AUTH MODE SWITCH
   ========================================================= */

function switchAuthMode(mode) {
    const login = getElement(
        "login-form",
        "login-section"
    );

    const register = getElement(
        "register-form",
        "register-section"
    );

    if (mode === "register") {
        if (login) {
            login.style.display = "none";
        }

        if (register) {
            register.style.display = "";
        }
    } else {
        if (register) {
            register.style.display = "none";
        }

        if (login) {
            login.style.display = "";
        }
    }
}


function setupAuthSwitches() {
    document.addEventListener("click", (event) => {
        const registerButton = event.target.closest(
            "#show-register, [data-auth='register'], .show-register"
        );

        const loginButton = event.target.closest(
            "#show-login, [data-auth='login'], .show-login"
        );

        if (registerButton) {
            event.preventDefault();
            switchAuthMode("register");
        }

        if (loginButton) {
            event.preventDefault();
            switchAuthMode("login");
        }
    });
}


/* =========================================================
   CHECK ACCOUNT
   ========================================================= */

async function checkAccount() {
    if (!getInitData()) {
        showAuthScreen();
        showToast(
            "Telegram se Mini App open karo.",
            "error"
        );
        return;
    }

    try {
        showLoading("Checking account...");

        const data = await api(
            "/api/miniapp/me",
            {
                method: "GET"
            }
        );

        if (data?.authenticated || data?.logged_in) {
            state.account =
                data.account ||
                data.user ||
                data;

            state.loggedIn = true;

            showAppScreen();

            await loadDashboard();

            return;
        }

        if (
            data?.registered === true ||
            data?.has_account === true
        ) {
            switchAuthMode("login");
        } else {
            switchAuthMode("register");
        }

        showAuthScreen();

    } catch (error) {
        console.error("Account check:", error);

        switchAuthMode("register");
        showAuthScreen();

    } finally {
        hideLoading();
    }
}


/* =========================================================
   REGISTER
   ========================================================= */

async function registerAccount(event) {
    if (event) {
        event.preventDefault();
    }

    const usernameInput = getElement(
        "register-username",
        "username",
        "regUsername"
    );

    const passwordInput = getElement(
        "register-password",
        "password",
        "regPassword"
    );

    const confirmInput = getElement(
        "register-confirm-password",
        "confirm-password",
        "confirmPassword",
        "regConfirmPassword"
    );

    const username =
        usernameInput?.value?.trim() || "";

    const password =
        passwordInput?.value || "";

    const confirmPassword =
        confirmInput?.value || "";

    if (!username) {
        showToast(
            "Username enter karo.",
            "error"
        );
        usernameInput?.focus();
        return;
    }

    if (!/^[A-Za-z0-9_]{3,32}$/.test(username)) {
        showToast(
            "Username 3-32 characters ka hona chahiye.",
            "error"
        );
        usernameInput?.focus();
        return;
    }

    if (password.length < 8) {
        showToast(
            "Password minimum 8 characters ka rakho.",
            "error"
        );
        passwordInput?.focus();
        return;
    }

    if (password !== confirmPassword) {
        showToast(
            "Passwords match nahi kar rahe.",
            "error"
        );
        confirmInput?.focus();
        return;
    }

    if (!getInitData()) {
        showToast(
            "Telegram Mini App data missing hai. App Telegram se open karo.",
            "error"
        );
        return;
    }

    try {
        showLoading("Creating your account...");

        const data = await api(
            "/api/miniapp/register",
            {
                method: "POST",
                body: JSON.stringify({
                    username,
                    password,
                    confirm_password: confirmPassword
                })
            }
        );

        if (
            data?.success ||
            data?.ok ||
            data?.registered
        ) {
            showToast(
                "Account successfully created! 🎉",
                "success"
            );

            state.account =
                data.account ||
                data.user ||
                null;

            state.loggedIn = true;

            showAppScreen();

            await loadDashboard();

            return;
        }

        throw new Error(
            data?.error ||
            data?.message ||
            "Registration failed."
        );

    } catch (error) {
        console.error("Register error:", error);

        showToast(
            error.message ||
            "Registration failed.",
            "error"
        );

    } finally {
        hideLoading();
    }
}


/* =========================================================
   LOGIN
   ========================================================= */

async function loginAccount(event) {
    if (event) {
        event.preventDefault();
    }

    const usernameInput = getElement(
        "login-username",
        "username",
        "loginUsername"
    );

    const passwordInput = getElement(
        "login-password",
        "password",
        "loginPassword"
    );

    const username =
        usernameInput?.value?.trim() || "";

    const password =
        passwordInput?.value || "";

    if (!username) {
        showToast(
            "Username enter karo.",
            "error"
        );
        usernameInput?.focus();
        return;
    }

    if (!password) {
        showToast(
            "Password enter karo.",
            "error"
        );
        passwordInput?.focus();
        return;
    }

    if (!getInitData()) {
        showToast(
            "Telegram Mini App data missing hai.",
            "error"
        );
        return;
    }

    try {
        showLoading("Logging in...");

        const data = await api(
            "/api/miniapp/login",
            {
                method: "POST",
                body: JSON.stringify({
                    username,
                    password
                })
            }
        );

        if (
            data?.success ||
            data?.ok ||
            data?.authenticated ||
            data?.logged_in
        ) {
            state.account =
                data.account ||
                data.user ||
                null;

            state.loggedIn = true;

            showToast(
                "Login successful! 👋",
                "success"
            );

            showAppScreen();

            await loadDashboard();

            return;
        }

        throw new Error(
            data?.error ||
            data?.message ||
            "Invalid username or password."
        );

    } catch (error) {
        console.error("Login error:", error);

        showToast(
            error.message ||
            "Login failed.",
            "error"
        );

    } finally {
        hideLoading();
    }
}


/* =========================================================
   FORM SETUP
   ========================================================= */

function setupAuthForms() {
    const registerForm = getElement(
        "register-form"
    );

    const loginForm = getElement(
        "login-form"
    );

    if (registerForm) {
        registerForm.addEventListener(
            "submit",
            registerAccount
        );
    }

    if (loginForm) {
        loginForm.addEventListener(
            "submit",
            loginAccount
        );
    }

    const registerButton = getElement(
        "register-btn",
        "registerButton"
    );

    if (registerButton) {
        registerButton.addEventListener(
            "click",
            registerAccount
        );
    }

    const loginButton = getElement(
        "login-btn",
        "loginButton"
    );

    if (loginButton) {
        loginButton.addEventListener(
            "click",
            loginAccount
        );
    }
}


/* =========================================================
   DASHBOARD
   ========================================================= */

async function loadDashboard() {
    try {
        const data = await api(
            "/api/miniapp/dashboard",
            {
                method: "GET"
            }
        );

        state.dashboard =
            data?.dashboard ||
            data;

        renderDashboard(
            state.dashboard
        );

    } catch (error) {
        console.error(
            "Dashboard error:",
            error
        );

        showToast(
            error.message ||
            "Dashboard load nahi hua.",
            "error"
        );
    }
}


function renderDashboard(data) {
    if (!data) {
        return;
    }

    const user =
        data.user ||
        data.profile ||
        state.account ||
        state.user ||
        {};

    const wallet =
        data.wallet ||
        data.coins ||
        {};

    const xp =
        data.xp ||
        data.level ||
        {};

    const values = {
        username:
            user.username ||
            state.account?.username ||
            state.user?.username ||
            "User",

        name:
            user.name ||
            user.full_name ||
            state.user?.first_name ||
            "User",

        coins:
            wallet.balance ??
            wallet.coins ??
            data.coins ??
            0,

        xp:
            xp.xp ??
            data.xp ??
            0,

        level:
            xp.level ??
            data.level ??
            1,

        rank:
            data.rank ??
            xp.rank ??
            "—"
    };

    setText(
        [
            "dashboard-username",
            "profile-username",
            "username-display"
        ],
        `@${values.username}`
    );

    setText(
        [
            "dashboard-name",
            "profile-name",
            "user-name"
        ],
        values.name
    );

    setText(
        [
            "coin-balance",
            "coins",
            "wallet-coins"
        ],
        formatNumber(values.coins)
    );

    setText(
        [
            "xp-value",
            "xp"
        ],
        formatNumber(values.xp)
    );

    setText(
        [
            "level-value",
            "level"
        ],
        values.level
    );

    setText(
        [
            "rank-value",
            "rank"
        ],
        values.rank
    );

    updateProfileAvatar(
        user.photo_url ||
        state.user?.photo_url
    );
}


/* =========================================================
   SHOP
   ========================================================= */

async function loadShop() {
    try {
        const data = await api(
            "/api/miniapp/shop",
            {
                method: "GET"
            }
        );

        state.shop =
            data?.items ||
            data?.shop ||
            [];

        renderShop(state.shop);

    } catch (error) {
        console.error(
            "Shop error:",
            error
        );

        showToast(
            error.message ||
            "Shop load nahi hua.",
            "error"
        );
    }
}


function renderShop(items) {
    const container = getElement(
        "shop-list",
        "shop-items",
        "shop-container"
    );

    if (!container) {
        retu
