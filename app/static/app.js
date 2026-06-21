"use strict";

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchButton = document.getElementById("search-button");
const voiceButton = document.getElementById("voice-button");
const clearButton = document.getElementById("clear-button");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");
const playerSection = document.getElementById("player-section");
const audioPlayer = document.getElementById("audio-player");
const playerCover = document.getElementById("player-cover");
const playerPlaceholder = document.getElementById("player-placeholder");
const nowPlaying = document.getElementById("now-playing");
const pauseButton = document.getElementById("pause-button");
const resumeButton = document.getElementById("resume-button");
const stopButton = document.getElementById("stop-button");
const historyPanel = document.getElementById("history-panel");
const refreshHistoryButton = document.getElementById("refresh-history-button");
const historyStatus = document.getElementById("history-status");
const playbackHistory = document.getElementById("playback-history");
const searchHistory = document.getElementById("search-history");

let currentTrack = null;
let activeRequest = null;

function setStatus(message, kind) {
  statusBox.textContent = message || "";
  statusBox.className = "status";
  if (kind) {
    statusBox.classList.add("status--" + kind);
  }
}

function setSearching(isSearching) {
  searchButton.disabled = isSearching;
  searchInput.disabled = isSearching;
  searchButton.innerHTML = isSearching
    ? "Buscando…"
    : '<span aria-hidden="true">⌕</span> Buscar';
}

function readApiError(response, payload) {
  if (payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  if (response.status === 422) {
    return "Escribe una canción para buscar.";
  }
  return "Ha ocurrido un problema al buscar. Inténtalo otra vez.";
}

function createResultCard(result, searchId) {
  const card = document.createElement("article");
  card.className = "result-card";

  const image = document.createElement("img");
  image.className = "result-card__thumbnail";
  image.src = result.thumbnail_url;
  image.alt = "";
  image.loading = "lazy";
  image.width = 480;
  image.height = 360;

  const body = document.createElement("div");
  body.className = "result-card__body";

  const title = document.createElement("h3");
  title.textContent = result.title;

  const channel = document.createElement("p");
  channel.className = "channel";
  channel.textContent = result.channel_title;

  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "play-button";
  playButton.textContent = "▶ Reproducir";
  playButton.setAttribute("aria-label", "Reproducir " + result.title);
  playButton.addEventListener("click", function () {
    playAudio(result, searchId);
  });

  body.append(title, channel, playButton);
  card.append(image, body);
  return card;
}

function renderResults(results, searchId) {
  resultsBox.replaceChildren();
  if (results.length === 0) {
    setStatus("No hemos encontrado canciones. Prueba con otras palabras.");
    return;
  }

  const fragment = document.createDocumentFragment();
  results.forEach(function (result) {
    fragment.appendChild(createResultCard(result, searchId));
  });
  resultsBox.appendChild(fragment);
  setStatus(results.length + (results.length === 1 ? " resultado" : " resultados"));
}

async function runSearch() {
  const query = searchInput.value.trim();
  if (!query) {
    setStatus("Escribe una canción para buscar.", "error");
    searchInput.focus();
    return;
  }

  if (activeRequest) {
    activeRequest.abort();
  }
  activeRequest = new AbortController();
  resultsBox.replaceChildren();
  setSearching(true);
  setStatus("Buscando…", "loading");

  try {
    const response = await fetch("/api/search?q=" + encodeURIComponent(query), {
      signal: activeRequest.signal,
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(function () { return null; });
    if (!response.ok) {
      throw new Error(readApiError(response, payload));
    }
    renderResults(
      Array.isArray(payload.results) ? payload.results : [],
      payload.search_id
    );
  } catch (error) {
    if (error.name !== "AbortError") {
      const message = error.message || "No se ha podido completar la búsqueda.";
      setStatus(message, "error");
    }
  } finally {
    setSearching(false);
    activeRequest = null;
  }
}

searchForm.addEventListener("submit", function (event) {
  event.preventDefault();
  runSearch();
});

searchInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    runSearch();
  }
});

clearButton.addEventListener("click", function () {
  if (activeRequest) {
    activeRequest.abort();
    activeRequest = null;
  }
  searchInput.value = "";
  resultsBox.replaceChildren();
  setSearching(false);
  setStatus("");
  searchInput.focus();
});

function enablePlayerControls() {
  pauseButton.disabled = false;
  resumeButton.disabled = false;
  stopButton.disabled = false;
}

function playAudio(video, searchId) {
  currentTrack = {
    videoId: video.video_id,
    title: video.title,
    searchId: searchId,
    recorded: false,
  };
  playerCover.src = video.thumbnail_url;
  playerCover.alt = "Portada de " + video.title;
  playerCover.hidden = false;
  playerPlaceholder.hidden = true;
  nowPlaying.textContent = "Suena: " + video.title;
  enablePlayerControls();
  setStatus("Preparando el audio…", "loading");

  audioPlayer.src = "/api/audio/" + encodeURIComponent(video.video_id);
  audioPlayer.load();
  const playback = audioPlayer.play();
  if (playback && typeof playback.catch === "function") {
    playback.catch(function () {
      setStatus("El audio está listo. Pulsa Reanudar para escucharlo.");
    });
  }
  playerSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function recordPlayback(searchId, videoId) {
  if (!Number.isInteger(searchId) || searchId <= 0) {
    return;
  }

  try {
    await fetch("/api/playback", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ search_id: searchId, video_id: videoId }),
      keepalive: true,
    });
  } catch (error) {
    console.warn("No se pudo guardar la reproducción.");
  }
}

audioPlayer.addEventListener("playing", function () {
  setStatus("Reproduciendo ♪");
  if (currentTrack && !currentTrack.recorded) {
    currentTrack.recorded = true;
    recordPlayback(currentTrack.searchId, currentTrack.videoId);
  }
});

audioPlayer.addEventListener("waiting", function () {
  setStatus("Preparando el audio…", "loading");
});

audioPlayer.addEventListener("ended", function () {
  if (currentTrack) {
    nowPlaying.textContent = "Terminó: " + currentTrack.title;
  }
  setStatus("");
});

audioPlayer.addEventListener("error", function () {
  if (audioPlayer.getAttribute("src")) {
    setStatus("No se ha podido reproducir esta canción. Prueba con otro resultado.", "error");
  }
});

pauseButton.addEventListener("click", function () {
  if (!audioPlayer.paused) {
    audioPlayer.pause();
    setStatus("En pausa");
  }
});

resumeButton.addEventListener("click", function () {
  if (audioPlayer.getAttribute("src")) {
    const playback = audioPlayer.play();
    if (playback && typeof playback.catch === "function") {
      playback.catch(function () {
        setStatus("No se ha podido reanudar el audio.", "error");
      });
    }
  }
});

stopButton.addEventListener("click", function () {
  audioPlayer.pause();
  audioPlayer.removeAttribute("src");
  audioPlayer.load();
  currentTrack = null;
  pauseButton.disabled = true;
  resumeButton.disabled = true;
  stopButton.disabled = true;
  nowPlaying.textContent = "Reproducción parada";
  setStatus("");
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = "es-ES";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  voiceButton.hidden = false;

  voiceButton.addEventListener("click", function () {
    try {
      recognition.start();
      voiceButton.classList.add("is-listening");
      voiceButton.textContent = "🎤 Te escucho…";
    } catch (error) {
      setStatus("El micrófono ya está escuchando.");
    }
  });

  recognition.addEventListener("result", function (event) {
    const transcript = event.results[0][0].transcript;
    searchInput.value = transcript;
    runSearch();
  });

  recognition.addEventListener("error", function (event) {
    if (event.error !== "no-speech" && event.error !== "aborted") {
      setStatus("No he podido usar el micrófono. Puedes escribir la canción.", "error");
    }
  });

  recognition.addEventListener("end", function () {
    voiceButton.classList.remove("is-listening");
    voiceButton.textContent = "🎤 Decir canción";
  });
}

function formatHistoryDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderPlaybackHistory(items) {
  playbackHistory.replaceChildren();
  if (items.length === 0) {
    playbackHistory.textContent = "Todavía no se ha reproducido ninguna canción.";
    return;
  }

  const fragment = document.createDocumentFragment();
  items.forEach(function (item) {
    const row = document.createElement("article");
    row.className = "history-item history-item--video";

    const image = document.createElement("img");
    image.src = item.thumbnail_url;
    image.alt = "";
    image.loading = "lazy";

    const text = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.title;
    const meta = document.createElement("span");
    meta.textContent = item.channel_title + " · " + formatHistoryDate(item.played_at);
    text.append(title, meta);

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "▶";
    button.setAttribute("aria-label", "Volver a reproducir " + item.title);
    button.addEventListener("click", function () {
      playAudio(item, item.search_id);
    });

    row.append(image, text, button);
    fragment.appendChild(row);
  });
  playbackHistory.appendChild(fragment);
}

function renderSearchHistory(items) {
  searchHistory.replaceChildren();
  if (items.length === 0) {
    searchHistory.textContent = "Todavía no hay búsquedas guardadas.";
    return;
  }

  const fragment = document.createDocumentFragment();
  items.forEach(function (item) {
    const row = document.createElement("article");
    row.className = "history-item";
    const text = document.createElement("div");
    const query = document.createElement("strong");
    query.textContent = item.query;
    const meta = document.createElement("span");
    const resultLabel = item.result_count === 1 ? " resultado" : " resultados";
    meta.textContent = item.result_count + resultLabel + " · " + formatHistoryDate(item.searched_at);
    text.append(query, meta);
    row.appendChild(text);
    fragment.appendChild(row);
  });
  searchHistory.appendChild(fragment);
}

async function loadHistory() {
  refreshHistoryButton.disabled = true;
  historyStatus.textContent = "Cargando historial…";
  try {
    const response = await fetch("/api/history?limit=20", {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error("No se ha podido cargar el historial.");
    }
    if (!payload.enabled) {
      historyStatus.textContent = "El historial está desactivado en este servidor.";
      renderPlaybackHistory([]);
      renderSearchHistory([]);
      return;
    }
    historyStatus.textContent = "";
    renderPlaybackHistory(Array.isArray(payload.playbacks) ? payload.playbacks : []);
    renderSearchHistory(Array.isArray(payload.searches) ? payload.searches : []);
  } catch (error) {
    historyStatus.textContent = error.message || "No se ha podido cargar el historial.";
  } finally {
    refreshHistoryButton.disabled = false;
  }
}

refreshHistoryButton.addEventListener("click", loadHistory);
historyPanel.addEventListener("toggle", function () {
  if (historyPanel.open) {
    loadHistory();
  }
});
