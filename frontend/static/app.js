/**
 * CurrículumIA — App JS
 * JWT stored in localStorage.
 * Screens: auth → gemini-key → upload → generate → result | paywall
 */

const API = "";  // same origin

// ── Affiliate tracking — capture ?aff= on any page load and persist ──
const _affParam = new URLSearchParams(window.location.search).get("aff");
if (_affParam) localStorage.setItem("aff", _affParam);

// ── State ──
let token = localStorage.getItem("token") || null;
let currentUser = null;
let baseResumePath = localStorage.getItem("baseResumePath") || null;
let pollingInterval = null;

// ── DOM helpers ──
const $ = (id) => document.getElementById(id);
const show = (id) => { const el = $(id); if (el) { el.classList.remove("hidden"); el.classList.add("active"); } };
const hide = (id) => { const el = $(id); if (el) { el.classList.add("hidden"); el.classList.remove("active"); } };
const showError = (id, msg) => { const el = $(id); if (el) { el.textContent = msg; el.classList.remove("hidden"); } };
const showErrorHTML = (id, html) => { const el = $(id); if (el) { el.innerHTML = html; el.classList.remove("hidden"); } };
const clearError = (id) => { const el = $(id); if (el) { el.textContent = ""; el.classList.add("hidden"); } };

// ── API helper ──
const _FETCH_TIMEOUT_MS = 30000;

async function apiFetch(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), _FETCH_TIMEOUT_MS);

  try {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(API + path, { ...options, headers, signal: controller.signal });
    clearTimeout(timeoutId);

    let data;
    try {
      data = await res.json();
    } catch {
      return { success: false, error: "El servidor devolvió una respuesta inválida. Intenta de nuevo." };
    }

    // Normalize FastAPI HTTPException format {"detail": "..."} to app format
    if (!res.ok && data.detail !== undefined && !("success" in data)) {
      return { success: false, error: data.detail };
    }
    return data;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      return { success: false, error: "La solicitud tardó demasiado tiempo. Verifica tu conexión e intenta de nuevo." };
    }
    return { success: false, error: "Error de conexión. Verifica tu internet e intenta de nuevo." };
  }
}

// ── Screens ──
const SCREENS = ["screen-auth", "screen-gemini", "screen-profile", "screen-upload", "screen-generate", "screen-result", "screen-paywall"];

function showScreen(screenId) {
  SCREENS.forEach((id) => {
    const el = $(id);
    if (el) { el.classList.remove("active"); el.classList.add("hidden"); }
  });
  const target = $(screenId);
  if (target) { target.classList.remove("hidden"); target.classList.add("active"); }
}

// ── Bootstrap ──
async function bootstrap() {
  // Check hash for register intent
  if (window.location.hash === "#register") {
    activateTab("register");
  }

  if (!token) { showScreen("screen-auth"); return; }

  const res = await apiFetch("/auth/me");
  if (!res.success) {
    // Only clear the session on a definitive auth rejection (bad/expired token).
    // A network or server error should not log the user out.
    const isAuthError = res.error && (
      res.error.includes("Token") ||
      res.error.includes("sesión") ||
      res.error.includes("no encontrado")
    );
    if (isAuthError) {
      logout();
    } else {
      showScreen("screen-auth");
    }
    return;
  }

  currentUser = res.data;
  $("user-email").textContent = currentUser.email;
  $("checkout-link").href = CHECKOUT_URL + "?checkout[email]=" + encodeURIComponent(currentUser.email);

  // Restore base resume path from server (survives logout/login and browser clears)
  if (currentUser.base_resume_path) {
    baseResumePath = currentUser.base_resume_path;
    localStorage.setItem("baseResumePath", baseResumePath);
  }

  // Route to correct screen
  if (!currentUser.has_gemini_key) {
    showScreen("screen-gemini");
    return;
  }

  if (!currentUser.has_profile) {
    prefillProfileForm();
    showScreen("screen-profile");
    return;
  }

  // Check subscription/paywall
  if (currentUser.tier === "exhausted") {
    showScreen("screen-paywall");
    return;
  }

  if (!baseResumePath) {
    showScreen("screen-upload");
  } else {
    $("resume-file-name").textContent = baseResumePath.split("/").pop();
    show("resume-file-info");
    showScreen("screen-generate");
  }
}

// ── Auth ──
function activateTab(tabName) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
  document.querySelector(`[data-tab="${tabName}"]`)?.classList.add("active");
  $(`tab-${tabName}`)?.classList.remove("hidden");
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

$("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("login-error");
  const res = await apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: $("login-email").value,
      password: $("login-password").value,
    }),
  });
  if (res.success) {
    token = res.data.access_token;
    localStorage.setItem("token", token);
    bootstrap();
  } else {
    showError("login-error", res.error || "Error al iniciar sesión.");
  }
});

$("form-register").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("reg-error");
  const aff = localStorage.getItem("aff") || "";
  const url = "/auth/register" + (aff ? `?aff=${encodeURIComponent(aff)}` : "");
  const res = await apiFetch(url, {
    method: "POST",
    body: JSON.stringify({
      email: $("reg-email").value,
      password: $("reg-password").value,
    }),
  });
  if (res.success) {
    localStorage.removeItem("aff");
    token = res.data.access_token;
    localStorage.setItem("token", token);
    bootstrap();
  } else {
    showError("reg-error", res.error || "Error al crear la cuenta.");
  }
});

// ── Logout ──
function logout() {
  token = null;
  currentUser = null;
  localStorage.clear();
  sessionStorage.clear();
  window.location.replace("/app.html");
}
$("btn-logout").addEventListener("click", logout);

// ── Gemini key ──
$("btn-save-key").addEventListener("click", async () => {
  clearError("gemini-error");
  const key = $("gemini-key-input").value.trim();
  if (!key) { showError("gemini-error", "Por favor ingresa tu API key."); return; }

  $("btn-save-key").disabled = true;
  $("btn-save-key").textContent = "Verificando…";

  const res = await apiFetch("/auth/gemini-key", {
    method: "POST",
    body: JSON.stringify({ api_key: key }),
  });

  $("btn-save-key").disabled = false;
  $("btn-save-key").textContent = "Guardar mi API key";

  if (res.success) {
    currentUser.has_gemini_key = true;
    showScreen("screen-upload");
  } else {
    showError("gemini-error", res.error || "Error al guardar la API key.");
  }
});

// ── Profile ──
function prefillProfileForm() {
  if (!currentUser) return;
  if (currentUser.resume_first_name) $("profile-first-name").value = currentUser.resume_first_name;
  if (currentUser.resume_last_name) $("profile-last-name").value = currentUser.resume_last_name;
  if (currentUser.resume_city) $("profile-city").value = currentUser.resume_city;
  if (currentUser.resume_phone) $("profile-phone").value = currentUser.resume_phone;
  $("profile-resume-email").value = currentUser.resume_email || currentUser.email || "";
  if (currentUser.resume_linkedin) $("profile-linkedin").value = currentUser.resume_linkedin;
}

$("form-profile").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError("profile-error");

  const btn = $("btn-save-profile");
  btn.disabled = true;
  btn.textContent = "Guardando…";

  const res = await apiFetch("/auth/profile", {
    method: "POST",
    body: JSON.stringify({
      first_name: $("profile-first-name").value.trim(),
      last_name: $("profile-last-name").value.trim(),
      city: $("profile-city").value.trim(),
      phone: $("profile-phone").value.trim(),
      resume_email: $("profile-resume-email").value.trim(),
      linkedin_url: $("profile-linkedin").value.trim() || null,
    }),
  });

  btn.disabled = false;
  btn.textContent = "Guardar y continuar";

  if (res.success) {
    currentUser.has_profile = true;
    currentUser.resume_first_name = $("profile-first-name").value.trim();
    currentUser.resume_last_name = $("profile-last-name").value.trim();
    currentUser.resume_city = $("profile-city").value.trim();
    currentUser.resume_phone = $("profile-phone").value.trim();
    currentUser.resume_email = $("profile-resume-email").value.trim();
    currentUser.resume_linkedin = $("profile-linkedin").value.trim() || null;

    if (!baseResumePath) {
      showScreen("screen-upload");
    } else {
      $("resume-file-name").textContent = baseResumePath.split("/").pop();
      show("resume-file-info");
      showScreen("screen-generate");
    }
  } else {
    showError("profile-error", res.error || "Error al guardar el perfil. Intenta de nuevo.");
  }
});

// ── Upload ──
const fileInput = $("resume-file");
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) {
    $("upload-label-text").textContent = file.name;
    $("btn-upload").disabled = false;
  }
});

$("btn-upload").addEventListener("click", async () => {
  clearError("upload-error");
  hide("upload-success");

  const file = fileInput.files[0];
  if (!file) { showError("upload-error", "Selecciona un archivo primero."); return; }
  if (!file.name.endsWith(".docx")) { showError("upload-error", "Solo se aceptan archivos .docx."); return; }

  $("btn-upload").disabled = true;
  $("btn-upload").textContent = "Subiendo…";

  const formData = new FormData();
  formData.append("file", file);

  let res;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), _FETCH_TIMEOUT_MS);
    const raw = await fetch(API + "/resume/upload", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    res = await raw.json();
  } catch (err) {
    $("btn-upload").disabled = false;
    $("btn-upload").textContent = "Subir currículum";
    showError("upload-error", err.name === "AbortError"
      ? "La subida tardó demasiado tiempo. Intenta de nuevo."
      : "Error de conexión al subir el archivo. Verifica tu internet e intenta de nuevo."
    );
    return;
  }

  $("btn-upload").disabled = false;
  $("btn-upload").textContent = "Subir currículum";

  if (res.success) {
    baseResumePath = res.data.file_path;
    localStorage.setItem("baseResumePath", baseResumePath);
    $("resume-file-name").textContent = file.name;
    show("resume-file-info");
    showScreen("screen-generate");
  } else {
    showError("upload-error", res.error || "Error al subir el archivo.");
  }
});

// ── Generate ──
$("btn-change-resume").addEventListener("click", () => {
  baseResumePath = null;
  localStorage.removeItem("baseResumePath");
  showScreen("screen-upload");
});

$("btn-generate").addEventListener("click", async () => {
  clearError("generate-error");
  const jd = $("job-desc").value.trim();
  if (!jd) { showError("generate-error", "Pega la descripción del puesto."); return; }
  if (!baseResumePath) { showError("generate-error", "Primero sube tu currículum base."); return; }

  $("btn-generate").disabled = true;
  show("generating-spinner");

  const targetCompany = $("target-company")?.value.trim() || "";
  const res = await apiFetch("/resume/generate", {
    method: "POST",
    body: JSON.stringify({ job_description: jd, base_resume_path: baseResumePath, target_company: targetCompany }),
  });

  if (!res.success) {
    $("btn-generate").disabled = false;
    hide("generating-spinner");

    // Paywall check
    if (res.error && (res.error.includes("Suscríbete") || res.error.includes("suscripción"))) {
      showScreen("screen-paywall");
    } else if (res.error && res.error.includes("API key de Gemini")) {
      showErrorHTML("generate-error", "Necesitas configurar tu API key de Gemini antes de generar. " + _SETTINGS_LINK);
    } else if (res.error && res.error.includes("perfil de contacto")) {
      prefillProfileForm();
      showScreen("screen-profile");
    } else {
      showError("generate-error", res.error || "Error al generar el currículum.");
    }
    return;
  }

  const generationId = res.data.generation_id;
  startPolling(generationId);
});

const _SETTINGS_LINK = '<a href="#" onclick="showScreen(\'screen-gemini\'); return false;" style="color:#DB3D44; text-decoration:underline;">Ir a configuración →</a>';

function _generationErrorMessage(errorCode) {
  switch (errorCode) {
    case "quota_exhausted":
      return "Alcanzaste el límite diario de tu API key de Gemini. Google restablece las cuotas gratuitas cada día a medianoche (hora del Pacífico). Vuelve a intentarlo mañana.";
    case "invalid_api_key":
      return "Tu API key de Gemini no es válida o fue revocada. " + _SETTINGS_LINK;
    case "timeout":
      return "La generación tardó demasiado tiempo. Por favor intenta de nuevo.";
    default:
      return "Hubo un error al generar tu currículum. Por favor intenta de nuevo.";
  }
}

function startPolling(generationId) {
  clearInterval(pollingInterval);
  let consecutiveFailures = 0;
  const MAX_POLL_FAILURES = 5;

  pollingInterval = setInterval(async () => {
    const res = await apiFetch(`/resume/generation/${generationId}`);

    if (!res.success) {
      consecutiveFailures++;
      if (consecutiveFailures >= MAX_POLL_FAILURES) {
        clearInterval(pollingInterval);
        $("btn-generate").disabled = false;
        hide("generating-spinner");
        showError("generate-error", "No se pudo verificar el estado de tu currículum. Verifica tu conexión e intenta de nuevo.");
      }
      return;
    }

    consecutiveFailures = 0;
    const gen = res.data;
    if (gen.status === "processing") return;  // still running

    clearInterval(pollingInterval);
    $("btn-generate").disabled = false;
    hide("generating-spinner");

    if (gen.status === "completed") {
      showResultScreen(gen);
    } else {
      showErrorHTML("generate-error", _generationErrorMessage(gen.error_code));
    }
  }, 3000);
}

function showResultScreen(gen) {
  if (gen.has_flagged_sections && gen.flagged_section_count > 0) {
    $("flagged-count").textContent = gen.flagged_section_count;
    show("flagged-banner");
  } else {
    hide("flagged-banner");
  }

  if (gen.download_url) {
    $("download-link").href = gen.download_url;
  }

  showScreen("screen-result");
}

// ── Result screen actions ──
$("btn-new-generation").addEventListener("click", () => {
  $("job-desc").value = "";
  showScreen("screen-generate");
});

// ── Paywall checkout link ──
// Replace this with your actual Lemon Squeezy checkout URL
const CHECKOUT_URL = "https://job-hunting.lemonsqueezy.com/checkout/buy/b56eb25b-b7db-494b-958c-d62096d72fd4";

// ── Init ──
bootstrap();
