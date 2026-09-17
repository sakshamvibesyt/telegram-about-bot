/* =========================================================
   SAKSHAM VIBES MINI APP
   APP.JS
========================================================= */

const tg = window.Telegram?.WebApp;

let currentUser = null;
let toastTimer = null;


/* =========================================================
   TELEGRAM INITIALIZATION
========================================================= */

function initTelegram() {
    if (!tg) {
        console.warn("Telegram WebApp is not available.");
        return;
    }

    tg.ready();
    tg.expand();

    if (tg.enableClosingConfirmation) {
        tg.enableClosingConfirmation();
    }

    applyTelegramTheme();

    if (tg.onEvent) {
        tg.onEvent("themeChanged", applyTelegramTheme);
    }

    autofillTelegramUsername();
}


/* =========================================================
   TELEGRAM THEME
========================================================= */

function applyTelegramTheme() {
    if (!tg) return;

    const root = document.documentElement;
    const theme = tg.themeParams || {};

    if (theme.bg_color) {
        root.style.setProperty("--tg-theme-bg-color", theme.bg_color);
    }

    if (theme.text_color) {
        root.style.setProperty("--tg-theme-text-color", theme.text_color);
    }
}


/* =========================================================
   TELEGRAM USER
========================================================= */

function getTelegramUser() {
    if (!tg || !tg.initDataUnsafe) {
        return null;
    }

    return tg.initDataUnsafe.user || null;
}


function getTelegramInitData() {
    if (!tg) return "";

    return tg.initData || "";
}


function autofillTelegramUsername() {
    const user = getTelegramUser();

    if (!user) return;

    if (user.username) {
        const username = user.username;

        const registerInput =
            document.getElementById("registerUsername");

        const loginInput =
            document.getElementById("loginUsername");

        if (registerInput && !registerInput.value) {
            registerInput.value = username;
        }

        if (loginInput && !loginInput.value) {
            loginInput.value = username;
        }
    }
}


/* =========================================================
   SCREEN HELPERS
========================================================= */

const screens = [
    "authScreen",
    "dashboardScreen",
    "profileScreen",
    "walletScreen",
    "shopScreen",
    "rewardsScreen",
    "referralScreen",
    "vipScreen",
    "activityScreen",
    "settingsScreen"
];


function hideAllScreens() {
    screens.forEach(id => {
        const element = document.getElementById(id);

        if (element) {
            element.classList.add("hidden");
        }
    });
}


function showScreen(id) {
    hideAllScreens();

    const element = document.getElementById(id);

    if (element) {
        element.classList.remove("hidden");
    }

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });
}


function showDashboard() {
    showScreen("dashboardScreen");
    setActiveNav(0);
}


function showAuth() {
    showScreen("authScreen");

    const nav = document.getElementById("bottomNav");

    if (nav) {
        nav.classList.add("hidden");
    }
}


/* =========================================================
   AUTH MODE
========================================================= */

function showRegister() {
    const registerBox =
        document.getElementById("registerBox");

    const loginBox =
        document.getElementById("loginBox");

    if (registerBox) {
        registerBox.classList.remove("hidden");
    }

    if (loginBox) {
        loginBox.classList.add("hidden");
    }

    clearAuthMessage();
    autofillTelegramUsername();
}


function showLogin() {
    const registerBox =
        document.getElementById("registerBox");

    const loginBox =
        document.getElementById("loginBox");

    if (registerBox) {
        registerBox.classList.add("hidden");
    }

    if (loginBox) {
        loginBox.classList.remove("hidden");
    }

    clearAuthMessage();
    autofillTelegramUsername();
}


/* =========================================================
   PASSWORD
========================================================= */

function togglePassword(inputId, button) {
    const input = document.getElementById(inputId);

    if (!input) return;

    if (input.type === "password") {
        input.type = "text";

        if (button) {
            button.textContent = "🙈";
        }
    } else {
        input.type = "password";

        if (button) {
            button.textContent = "👁";
        }
    }
}


/* =========================================================
   AUTH MESSAGE
========================================================= */

function showAuthMessage(message, type = "error") {
    const box =
        document.getElementById("authMessage");

    if (!box) return;

    box.textContent = message;
    box.classList.remove("hidden");

    if (type === "success") {
        box.style.background =
            "rgba(53, 208, 127, 0.08)";

        box.style.borderColor =
            "rgba(53, 208, 127, 0.15)";

        box.style.color = "#72e5a8";
    } else {
        box.style.background =
            "rgba(255, 95, 109, 0.08)";

        box.style.borderColor =
            "rgba(255, 95, 109, 0.15)";

        box.style.color = "#ff9ca5";
    }
}


function clearAuthMessage() {
    const box =
        document.getElementById("authMessage");

    if (!box) return;

    box.classList.add("hidden");
    box.textContent = "";
}


/* =========================================================
   API
========================================================= */

async function apiRequest(url, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
    };

    const initData = getTelegramInitData();

    if (initData) {
        headers["X-Telegram-Init-Data"] = initData;
    }

    const response = await fetch(url, {
        ...options,
        headers,
        credentials: "include"
    });

    let data = null;

    try {
        data = await response.json();
    } catch {
        data = {
            ok: false,
            error: "Invalid server response."
        };
    }

    if (!response.ok) {
        throw new Error(
            data.error ||
            data.message ||
            `Request failed (${response.status})`
        );
    }

    return data;
}


/* =========================================================
   REGISTER
========================================================= */

async function registerAccount() {
    clearAuthMessage();

    const usernameInput =
        document.getElementById("registerUsername");

    const passwordInput =
        document.getElementById("registerPassword");

    const confirmInput =
        document.getElementById("registerConfirm");

    const username =
        usernameInput?.value.trim().replace(/^@/, "");

    const password =
        passwordInput?.value || "";

    const confirm =
        confirmInput?.value || "";

    if (!username) {
        showAuthMessage(
            "Please enter a username."
        );
        return;
    }

    if (!/^[a-zA-Z0-9_]{3,32}$/.test(username)) {
        showAuthMessage(
            "Username must be 3–32 characters and use only letters, numbers or underscore."
        );
        return;
    }

    if (!password) {
        showAuthMessage(
            "Please create a password."
        );
        return;
    }

    if (password.length < 6) {
        showAuthMessage(
            "Password must contain at least 6 characters."
        );
        return;
    }

    if (password !== confirm) {
        showAuthMessage(
            "Passwords do not match."
        );
        return;
    }

    const button =
        document.getElementById("registerBtn");

    setButtonLoading(button, true);

    try {
        const result = await apiRequest(
            "/api/miniapp/register",
            {
                method: "POST",
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            }
        );

        if (!result.ok) {
            throw new Error(
                result.error ||
                "Registration failed."
            );
        }

        showAuthMessage(
            "Account created successfully. Opening dashboard...",
            "success"
        );

        if (result.user) {
            currentUser = result.user;
        }

        setTimeout(() => {
            loadDashboard();
        }, 600);

    } catch (error) {
        showAuthMessage(
            error.message ||
            "Unable to create account."
        );
    } finally {
        setButtonLoading(button, false);
    }
}


/* =========================================================
   LOGIN
========================================================= */

async function loginAccount() {
    clearAuthMessage();

    const usernameInput =
        document.getElementById("loginUsername");

    const passwordInput =
        document.getElementById("loginPassword");

    const username =
        usernameInput?.value.trim().replace(/^@/, "");

    const password =
        passwordInput?.value || "";

    if (!username) {
        showAuthMessage(
            "Please enter your username."
        );
        return;
    }

    if (!password) {
        showAuthMessage(
            "Please enter your password."
        );
        return;
    }

    const button =
        document.getElementById("loginBtn");

    setButtonLoading(button, true);

    try {
        const result = await apiRequest(
            "/api/miniapp/login",
            {
                method: "POST",
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            }
        );

        if (!result.ok) {
            throw new Error(
                result.error ||
                "Login failed."
            );
        }

        currentUser = result.user || null;

        showToast(
            "success",
            "Login successful"
        );

        await loadDashboard();

    } catch (error) {
        showAuthMessage(
            error.message ||
            "Unable to login."
        );
    } finally {
        setButtonLoading(button, false);
    }
}


/* =========================================================
   SESSION CHECK
========================================================= */

async function checkSession() {
    try {
        const result = await apiRequest(
            "/api/miniapp/me",
            {
                method: "GET"
            }
        );

        if (result.ok && result.authenticated) {
            currentUser = result.user || null;

            await loadDashboard();
            return true;
        }

        showAuth();
        return false;

    } catch (error) {
        console.warn(
            "Session check failed:",
            error
        );

        showAuth();
        return false;
    }
}


/* =========================================================
   DASHBOARD
========================================================= */

async function loadDashboard() {
    showLoading(
        "Loading your dashboard..."
    );

    try {
        const result = await apiRequest(
            "/api/miniapp/dashboard",
            {
                method: "GET"
            }
        );

        if (!result.ok) {
            throw new Error(
                result.error ||
                "Unable to load dashboard."
            );
        }

        if (result.user) {
            currentUser = result.user;
        }

        renderDashboard(result);

        showScreen("dashboardScreen");

        const nav =
            document.getElementById("bottomNav");

        if (nav) {
            nav.classList.remove("hidden");
        }

        setActiveNav(0);

    } catch (error) {
        console.warn(error);

        /*
         * During the frontend-only stage the backend may not
         * exist yet. We keep the interface usable instead of
         * breaking the entire Mini App.
         */
        if (currentUser) {
            renderDashboard({
                user: currentUser,
                coins: currentUser.coins || 0,
                xp: currentUser.xp || 0,
                level: currentUser.level || 1,
                rank: currentUser.rank || "—"
            });

            showScreen("dashboardScreen");

            const nav =
                document.getElementById("bottomNav");

            if (nav) {
                nav.classList.remove("hidden");
            }

            setActiveNav(0);
        } else {
            showAuth();

            showAuthMessage(
                error.message ||
                "Please login again."
            );
        }

    } finally {
        hideLoading();
    }
}


/* =========================================================
   RENDER DASHBOARD
========================================================= */

function renderDashboard(data) {
    const user = data.user || currentUser || {};

    currentUser = {
        ...currentUser,
        ...user
    };

    const username =
        cleanUsername(
            user.username ||
            currentUser.username ||
            "user"
        );

    const firstName =
        user.first_name ||
        user.firstName ||
        currentUser.first_name ||
        currentUser.firstName ||
        username;

    const coins =
        numberValue(
            data.coins ??
            user.coins ??
            currentUser.coins ??
            0
        );

    const xp =
        numberValue(
            data.xp ??
            user.xp ??
            currentUser.xp ??
            0
        );

    const level =
        numberValue(
            data.level ??
            user.level ??
            currentUser.level ??
            1
        );

    const rank =
        data.rank ??
        user.rank ??
        currentUser.rank ??
        "—";

    const messages =
        numberValue(
            data.messages ??
            user.messages ??
            currentUser.messages ??
            0
        );

    const vip =
        Boolean(
            data.vip ??
            user.vip ??
            currentUser.vip ??
            false
        );

    const elite =
        Boolean(
            data.elite ??
            user.elite ??
            currentUser.elite ??
            false
        );

    setText(
        "headerName",
        firstName
    );

    setText(
        "heroUsername",
        `@${username}`
    );

    setText(
        "coinsValue",
        formatNumber(coins)
    );

    setText(
        "levelValue",
        level
    );

    setText(
        "xpValue",
        formatNumber(xp)
    );

    setText(
        "rankValue",
        rank
    );

    setText(
        "profileName",
        firstName
    );

    setText(
        "profileUsername",
        `@${username}`
    );

    setText(
        "profileUsername2",
        `@${username}`
    );

    setText(
        "profileTelegramId",
        user.telegram_id ||
        user.telegramId ||
        currentUser.telegram_id ||
        "—"
    );

    setText(
        "profileLevel",
        level
    );

    setText(
        "profileXP",
        formatNumber(xp)
    );

    setText(
        "profileCoins",
        formatNumber(coins)
    );

    setText(
        "walletCoins",
        formatNumber(coins)
    );

    setText(
        "shopCoins",
        formatNumber(coins)
    );

    setText(
        "activityXP",
        formatNumber(xp)
    );

    setText(
        "activityMessages",
        formatNumber(messages)
    );

    setText(
        "activityRank",
        rank
    );

    setText(
        "vipStatus",
        vip ? "ACTIVE" : "INACTIVE"
    );

    setText(
        "eliteStatus",
        elite ? "ACTIVE" : "INACTIVE"
    );

    updateProfileBadge(
        vip,
        elite
    );

    updateAvatar(
        firstName,
        user.photo_url ||
        user.photoUrl ||
        null
    );

    updateXPProgress(
        xp,
        level,
        data.next_level_xp ||
        data.nextLevelXP ||
        null
    );

    if (data.referral_link) {
        setText(
            "referralLink",
            data.referral_link
        );
    }

    renderShop(
        data.shop ||
        data.shop_items ||
        []
    );
}


/* =========================================================
   PROFILE
========================================================= */

async function openProfile() {
    showScreen("profileScreen");
    setActiveNav(3);

    if (currentUser) {
        updateProfileFromUser(currentUser);
    }
}


function updateProfileFromUser(user) {
    const name =
        user.first_name ||
        user.firstName ||
        user.username ||
        "User";

    const username =
        cleanUsername(
            user.username ||
            "user"
        );

    setText(
        "profileName",
        name
    );

    setText(
        "profileUsername",
        `@${username}`
    );

    setText(
        "profileUsername2",
        `@${username}`
    );

    setText(
        "profileTelegramId",
        user.telegram_id ||
        user.telegramId ||
        "—"
    );

    setText(
        "profileLevel",
        user.level || 1
    );

    setText(
        "profileXP",
        formatNumber(user.xp || 0)
    );

    setText(
        "profileCoins",
        formatNumber(user.coins || 0)
    );
}


/* =========================================================
   WALLET
========================================================= */

async function openWallet() {
    showScreen("walletScreen");
    setActiveNav(1);

    if (currentUser) {
        setText(
            "walletCoins",
            formatNumber(
                currentUser.coins || 0
            )
        );
    }
}


/* =========================================================
   SHOP
========================================================= */

async function openShop() {
    showScreen("shopScreen");
    setActiveNav(2);

    try {
        const result = await apiRequest(
            "/api/miniapp/shop",
            {
                method: "GET"
            }
        );

        if (result.ok) {
            renderShop(
                result.items ||
                result.shop ||
                []
            );

            if (result.coins !== undefined) {
                setText(
                    "shopCoins",
                    formatNumber(result.coins)
                );
            }
        }

    } catch (error) {
        console.warn(
            "Shop request failed:",
            error
        );
    }
}


function renderShop(items) {
    const container =
        document.getElementById("shopItems");

    if (!container) return;

    if (!Array.isArray(items) || items.length === 0) {
        container.innerHTML = `
            <div class="empty-card">
                🛍️
                <p>
                    No shop items available right now.
                </p>
            </div>
        `;

        return;
    }

    container.innerHTML = "";

    items.forEach(item => {
        const card =
            document.createElement("div");

        card.className = "menu-card";

        const name =
            escapeHTML(
                item.name ||
                item.title ||
                "Reward"
            );

        const description =
            escapeHTML(
                item.description ||
                "Community reward"
            );

        const price =
            formatNumber(
                item.price || 0
            );

        card.innerHTML = `
            <div class="menu-icon">
                🛍️
            </div>

            <div class="menu-in
