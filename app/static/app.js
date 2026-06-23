"use strict";

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchButton = document.getElementById("search-button");
const voiceButton = document.getElementById("voice-button");
const clearButton = document.getElementById("clear-button");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");
const playFavoritesButton = document.getElementById("play-favorites-button");
const favoritesEmpty = document.getElementById("favorites-empty");
const favoritesList = document.getElementById("favorites-list");
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
let activePlaylist = null;
let favoritesEnabled = false;
let favoriteTracks = [];

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

function readFavoriteApiError(response, payload) {
  if (payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  if (response.status === 503) {
    return "Las favoritas requieren PostgreSQL en este servidor.";
  }
  return "No se han podido guardar las favoritas.";
}

function getSearchId(video, searchId) {
  if (Number.isInteger(searchId) && searchId > 0) {
    return searchId;
  }
  if (video && Number.isInteger(video.search_id) && video.search_id > 0) {
    return video.search_id;
  }
  return null;
}

function normaliseFavoriteTrack(item) {
  if (!item || typeof item !== "object") {
    return null;
  }

  const videoId = typeof item.video_id === "string" ? item.video_id.trim() : "";
  if (!videoId) {
    return null;
  }

  return {
    video_id: videoId,
    title:
      typeof item.title === "string" && item.title.trim()
        ? item.title.trim()
        : "Canción sin título",
    channel_title:
      typeof item.channel_title === "string" ? item.channel_title.trim() : "",
    thumbnail_url:
      typeof item.thumbnail_url === "string" ? item.thumbnail_url.trim() : "",
    search_id: getSearchId(item),
    favorited_at:
      typeof item.favorited_at === "string"
        ? item.favorited_at
        : new Date().toISOString(),
  };
}

function getFavoriteIndex(videoId) {
  return favoriteTracks.findIndex(function (track) {
    return track.video_id === videoId;
  });
}

function isFavorite(videoId) {
  return getFavoriteIndex(videoId) !== -1;
}

function favoriteFromVideo(video, searchId) {
  if (!video || typeof video.video_id !== "string") {
    return null;
  }

  return normaliseFavoriteTrack({
    video_id: video.video_id,
    title: video.title,
    channel_title: video.channel_title,
    thumbnail_url: video.thumbnail_url,
    search_id: getSearchId(video, searchId),
    favorited_at: new Date().toISOString(),
  });
}

function setFavoriteButtonState(button, favorited) {
  const title = button.dataset.favoriteTitle || "esta canción";
  button.disabled = !favoritesEnabled;
  button.classList.toggle("is-favorite", favorited);
  button.setAttribute("aria-pressed", String(favorited));
  button.textContent = favorited ? "★ Favorita" : "☆ Favorita";
  button.setAttribute(
    "aria-label",
    favorited
      ? "Quitar " + title + " de favoritas"
      : "Añadir " + title + " a favoritas"
  );
}

function updateFavoriteButtons(videoId) {
  document.querySelectorAll("[data-favorite-video-id]").forEach(function (button) {
    if (!videoId || button.dataset.favoriteVideoId === videoId) {
      setFavoriteButtonState(button, isFavorite(button.dataset.favoriteVideoId));
    }
  });
}

function upsertFavoriteTrack(track) {
  const existingIndex = getFavoriteIndex(track.video_id);
  if (existingIndex === -1) {
    favoriteTracks.unshift(track);
  } else {
    favoriteTracks.splice(existingIndex, 1, track);
  }
}

async function toggleFavorite(video, searchId) {
  const favorite = favoriteFromVideo(video, searchId);
  if (!favorite) {
    return;
  }
  if (!favoritesEnabled) {
    setStatus("Las favoritas requieren PostgreSQL en este servidor.", "error");
    return;
  }

  const removing = isFavorite(favorite.video_id);
  setStatus("Guardando favoritas…", "loading");

  try {
    const response = await fetch(
      removing
        ? "/api/favorites/" + encodeURIComponent(favorite.video_id)
        : "/api/favorites",
      removing
        ? { method: "DELETE", headers: { Accept: "application/json" } }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify(favorite),
          }
    );
    const payload = await response.json().catch(function () { return null; });
    if (!response.ok) {
      throw new Error(readFavoriteApiError(response, payload));
    }

    if (removing) {
      favoriteTracks = favoriteTracks.filter(function (track) {
        return track.video_id !== favorite.video_id;
      });
      setStatus("Quitada de favoritas.");
    } else {
      const saved = normaliseFavoriteTrack(payload && payload.favorite) || favorite;
      upsertFavoriteTrack(saved);
      setStatus("Añadida a favoritas.");
    }

    renderFavorites();
    updateFavoriteButtons(favorite.video_id);
  } catch (error) {
    setStatus(error.message || "No se han podido guardar las favoritas.", "error");
    loadFavorites();
  }
}

function createFavoriteButton(video, searchId) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "favorite-button";
  button.dataset.favoriteVideoId = video.video_id;
  button.dataset.favoriteTitle = video.title;
  setFavoriteButtonState(button, isFavorite(video.video_id));
  button.addEventListener("click", function () {
    toggleFavorite(video, searchId);
  });
  return button;
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

  const actions = document.createElement("div");
  actions.className = "result-card__actions";
  actions.append(playButton, createFavoriteButton(result, searchId));

  body.append(title, channel, actions);
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

function createFavoriteItem(track, index) {
  const row = document.createElement("article");
  row.className = "favorite-item";

  let media;
  if (track.thumbnail_url) {
    media = document.createElement("img");
    media.src = track.thumbnail_url;
    media.alt = "";
    media.loading = "lazy";
  } else {
    media = document.createElement("div");
    media.className = "favorite-item__placeholder";
    media.textContent = "♪";
    media.setAttribute("aria-hidden", "true");
  }

  const text = document.createElement("div");
  text.className = "favorite-item__text";
  const title = document.createElement("strong");
  title.textContent = track.title;
  const channel = document.createElement("span");
  channel.textContent = track.channel_title || "Canal desconocido";
  text.append(title, channel);

  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "favorite-icon-button";
  playButton.textContent = "▶";
  playButton.setAttribute("aria-label", "Reproducir favoritas desde " + track.title);
  playButton.addEventListener("click", function () {
    playFavoriteQueue(index);
  });

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "favorite-icon-button favorite-icon-button--remove";
  removeButton.textContent = "★";
  removeButton.setAttribute("aria-label", "Quitar " + track.title + " de favoritas");
  removeButton.addEventListener("click", function () {
    toggleFavorite(track, track.search_id);
  });

  row.append(media, text, playButton, removeButton);
  return row;
}

function renderFavorites() {
  favoritesList.replaceChildren();
  playFavoritesButton.disabled = !favoritesEnabled || favoriteTracks.length === 0;
  favoritesEmpty.hidden = favoriteTracks.length > 0;

  if (!favoritesEnabled) {
    favoritesEmpty.hidden = false;
    favoritesEmpty.textContent = "Favoritas no disponibles: PostgreSQL no está activo.";
    return;
  }

  if (favoriteTracks.length === 0) {
    favoritesEmpty.textContent = "Aún no hay canciones favoritas.";
    return;
  }

  const fragment = document.createDocumentFragment();
  favoriteTracks.forEach(function (track, index) {
    fragment.appendChild(createFavoriteItem(track, index));
  });
  favoritesList.appendChild(fragment);
}

async function loadFavorites() {
  favoritesEnabled = false;
  playFavoritesButton.disabled = true;
  favoritesEmpty.hidden = false;
  favoritesEmpty.textContent = "Cargando favoritas…";
  try {
    const response = await fetch("/api/favorites", {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json().catch(function () { return null; });
    if (!response.ok) {
      throw new Error(readFavoriteApiError(response, payload));
    }

    favoritesEnabled = Boolean(payload && payload.enabled);
    favoriteTracks = Array.isArray(payload && payload.favorites)
      ? payload.favorites
          .map(normaliseFavoriteTrack)
          .filter(function (track) { return track !== null; })
      : [];
    renderFavorites();
    updateFavoriteButtons();
  } catch (error) {
    favoritesEnabled = false;
    favoriteTracks = [];
    renderFavorites();
    favoritesEmpty.textContent = error.message || "No se han podido cargar las favoritas.";
    updateFavoriteButtons();
  }
}

function playFavoriteQueue(startIndex) {
  if (favoriteTracks.length === 0) {
    setStatus("Marca canciones como favoritas para crear la lista.", "error");
    return;
  }

  const tracks = favoriteTracks.slice();
  const index = Math.max(0, Math.min(startIndex || 0, tracks.length - 1));
  activePlaylist = { tracks: tracks, index: index };
  playAudio(tracks[index], tracks[index].search_id, { fromPlaylist: true });
}

function playNextFavorite() {
  if (!activePlaylist) {
    return false;
  }

  const nextIndex = activePlaylist.index + 1;
  if (nextIndex >= activePlaylist.tracks.length) {
    activePlaylist = null;
    nowPlaying.textContent = "Terminó la lista de favoritas";
    setStatus("Lista de favoritas terminada.");
    return true;
  }

  activePlaylist.index = nextIndex;
  playAudio(
    activePlaylist.tracks[nextIndex],
    activePlaylist.tracks[nextIndex].search_id,
    { fromPlaylist: true, scroll: false }
  );
  return true;
}

playFavoritesButton.addEventListener("click", function () {
  playFavoriteQueue(0);
});

function enablePlayerControls() {
  pauseButton.disabled = false;
  resumeButton.disabled = false;
  stopButton.disabled = false;
}

function playAudio(video, searchId, options) {
  const playbackOptions = options || {};
  if (!playbackOptions.fromPlaylist) {
    activePlaylist = null;
  }

  currentTrack = {
    videoId: video.video_id,
    title: video.title,
    searchId: getSearchId(video, searchId),
    recorded: false,
  };
  if (video.thumbnail_url) {
    playerCover.src = video.thumbnail_url;
    playerCover.alt = "Portada de " + video.title;
    playerCover.hidden = false;
    playerPlaceholder.hidden = true;
  } else {
    playerCover.removeAttribute("src");
    playerCover.hidden = true;
    playerPlaceholder.hidden = false;
  }
  nowPlaying.textContent = activePlaylist
    ? "Favoritas " + (activePlaylist.index + 1) + "/" + activePlaylist.tracks.length + ": " + video.title
    : "Suena: " + video.title;
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
  if (playbackOptions.scroll !== false) {
    playerSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }
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
  if (playNextFavorite()) {
    return;
  }
  setStatus("");
});

audioPlayer.addEventListener("error", function () {
  if (audioPlayer.getAttribute("src")) {
    if (activePlaylist) {
      if (activePlaylist.index + 1 < activePlaylist.tracks.length) {
        setStatus("No se ha podido reproducir esta favorita. Pasando a la siguiente.", "error");
        window.setTimeout(playNextFavorite, 900);
        return;
      }
      activePlaylist = null;
      nowPlaying.textContent = "Terminó la lista de favoritas";
    }
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
  activePlaylist = null;
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

loadFavorites();
