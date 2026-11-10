// ==============================
// NEST + THERMOCOUPLE + STOVE WATCH (NO AI)
// ==============================

/**********************
 * CONFIG
 **********************/
const CFG = {
  SPREADSHEET_ID: 'YOUR_SPREADSHEET_ID',
  DEVICE_ACCESS_PROJECT_ID: 'YOUR_DEVICE_ACCESS_PROJECT_ID',
  OAUTH_CLIENT_ID: 'YOUR_OAUTH_CLIENT_ID',
  OAUTH_CLIENT_SECRET: 'YOUR_OAUTH_CLIENT_SECRET',
  REDIRECT_URI: 'https://www.google.com',

  // Your latitude and longitude (used to find the nearest weather station)
  NWS_LAT: 0.0000,
  NWS_LON: 0.0000,
  NWS_USER_AGENT: 'NestSheetsLogger (your_email@example.com)',

  // Thermocouple endpoint token
  THERMO_TOKEN: 'YOUR_SHARED_TOKEN',
  THERMO_LATEST_KEY: 'THERMO_LATEST',
};

const UP = PropertiesService.getUserProperties();
const SP = PropertiesService.getScriptProperties();

const STOVE = {
  WATCH_SHEET: 'stove_watch',
  EVENTS_SHEET: 'stove_events',
};

/*************************************************************
 * MENU
 *************************************************************/
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Stove Watch')
    .addItem('Open panel', 'openStoveWatchSidebar')
    .addItem('Clear stove_watch log', 'stoveWatchClear')
    .addSeparator()
    .addItem('Setup sheets (stove_watch + stove_events)', 'stoveSetup')
    .addItem('Create 5-min Nest trigger', 'create5MinTrigger')
    .addToUi();
}

/*************************************************************
 * SIDEBAR
 *************************************************************/
function openStoveWatchSidebar() {
  const html = HtmlService.createHtmlOutputFromFile('StoveWatch')
    .setTitle('Stove Watch');
  SpreadsheetApp.getUi().showSidebar(html);
}

/*************************************************************
 * THERMOCOUPLE RECEIVER (Web App)
 * Pico sends: ?token=...&fault=...&cj=...&tc=...
 *************************************************************/
function doGet(e) { return handleThermo_(e); }
function doPost(e) { return handleThermo_(e); }

function handleThermo_(e) {
  try {
    let token, fault, cj, tc;

    if (e && e.parameter && Object.keys(e.parameter).length) {
      const p = e.parameter;
      token = p.token;
      fault = p.fault;
      cj = p.cj;
      tc = p.tc;
    } else if (e && e.postData && e.postData.contents) {
      const data = JSON.parse(e.postData.contents || "{}");
      token = data.token;
      fault = data.fault;
      cj = data.cj;
      tc = data.tc;
    }

    if (!token) return ContentService.createTextOutput("missing token").setMimeType(ContentService.MimeType.TEXT);
    if (token !== CFG.THERMO_TOKEN) return ContentService.createTextOutput("unauthorized").setMimeType(ContentService.MimeType.TEXT);

    const sample = {
      ts: Date.now(),
      fault: Number(fault),
      cj: Number(cj),
      tc: Number(tc),
    };

    SP.setProperty(CFG.THERMO_LATEST_KEY, JSON.stringify(sample));
    return ContentService.createTextOutput("ok").setMimeType(ContentService.MimeType.TEXT);

  } catch (err) {
    return ContentService
      .createTextOutput("error: " + String(err?.message || err))
      .setMimeType(ContentService.MimeType.TEXT);
  }
}

function getLatestThermo_() {
  const s = SP.getProperty(CFG.THERMO_LATEST_KEY);
  if (!s) return null;
  try { return JSON.parse(s); } catch { return null; }
}

/*************************************************************
 * NEST AUTH + SDM
 *************************************************************/
function resetNestAuth() {
  UP.deleteProperty('NEST_REFRESH_TOKEN');
  UP.deleteProperty('NEST_ACCESS_TOKEN');
  UP.deleteProperty('NEST_ACCESS_EXPIRES_AT');
  Logger.log('Cleared Nest tokens.');
}

function exchangeAuthCodeOnce() {
  const authCode = 'PASTE_AUTH_CODE_HERE';

  const resp = UrlFetchApp.fetch('https://oauth2.googleapis.com/token', {
    method: 'post',
    payload: {
      client_id: CFG.OAUTH_CLIENT_ID,
      client_secret: CFG.OAUTH_CLIENT_SECRET,
      code: authCode,
      grant_type: 'authorization_code',
      redirect_uri: CFG.REDIRECT_URI,
    },
    muteHttpExceptions: true,
  });

  const json = JSON.parse(resp.getContentText());
  if (!json.refresh_token) throw new Error('No refresh_token returned:\n' + resp.getContentText());

  UP.setProperty('NEST_REFRESH_TOKEN', json.refresh_token);
  UP.deleteProperty('NEST_ACCESS_TOKEN');
  UP.deleteProperty('NEST_ACCESS_EXPIRES_AT');
  Logger.log('Saved refresh token.');
}

function getAccessToken_() {
  const cached = UP.getProperty('NEST_ACCESS_TOKEN');
  const expiresAt = Number(UP.getProperty('NEST_ACCESS_EXPIRES_AT') || 0);
  if (cached && Date.now() < (expiresAt - 120000)) return cached;

  const refreshToken = UP.getProperty('NEST_REFRESH_TOKEN');
  if (!refreshToken) throw new Error('Missing refresh token. Run exchangeAuthCodeOnce().');

  const resp = UrlFetchApp.fetch('https://oauth2.googleapis.com/token', {
    method: 'post',
    payload: {
      client_id: CFG.OAUTH_CLIENT_ID,
      client_secret: CFG.OAUTH_CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: 'refresh_token',
    },
    muteHttpExceptions: true,
  });

  const json = JSON.parse(resp.getContentText());
  if (!json.access_token) throw new Error('Failed to refresh access token:\n' + resp.getContentText());

  UP.setProperty('NEST_ACCESS_TOKEN', json.access_token);
  UP.setProperty('NEST_ACCESS_EXPIRES_AT', String(Date.now() + (json.expires_in || 0) * 1000));
  return json.access_token;
}

function sdmGet_(path) {
  const url = 'https://smartdevicemanagement.googleapis.com/v1' + path;
  const resp = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + getAccessToken_() },
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  const text = resp.getContentText();
  if (code < 200 || code >= 300) throw new Error(`SDM GET ${path} failed (${code}):\n${text}`);
  return JSON.parse(text);
}

function setDeviceName() {
  // Paste the device name you get from listNestDevices()
  const deviceName = 'enterprises/PROJECT_ID/devices/DEVICE_ID';
  UP.setProperty('NEST_DEVICE_NAME', deviceName);
  Logger.log('Saved NEST_DEVICE_NAME');
}

function listNestDevices() {
  const projectId = CFG.DEVICE_ACCESS_PROJECT_ID;
  const data = sdmGet_(`/enterprises/${projectId}/devices`);
  Logger.log(JSON.stringify(data, null, 2));
  return data;
}

/*************************************************************
 * NWS (Outdoor temp)
 *************************************************************/
function getLisbonOutdoorTempF_() {
  const lat = CFG.NWS_LAT.toFixed(4);
  const lon = CFG.NWS_LON.toFixed(4);

  const cache = CacheService.getScriptCache();
  const cacheKey = `nws_station_${lat}_${lon}`;
  let stationId = cache.get(cacheKey);

  if (!stationId) {
    const points = nwsGetJson_(`/points/${lat},${lon}`);
    const stationsUrl = points?.properties?.observationStations;
    if (!stationsUrl) return '';

    const stations = nwsFetchJsonUrl_(stationsUrl);
    const first = stations?.features?.[0];
    stationId = first?.properties?.stationIdentifier;
    if (!stationId) return '';

    cache.put(cacheKey, stationId, 60 * 60 * 24 * 7);
  }

  const obs = nwsGetJson_(`/stations/${stationId}/observations/latest`);
  const tempC = obs?.properties?.temperature?.value;
  if (typeof tempC !== 'number') return '';

  return Math.round(tempC * 9/5 + 32);
}

function nwsGetJson_(path) {
  return nwsFetchJsonUrl_('https://api.weather.gov' + path);
}

function nwsFetchJsonUrl_(url) {
  const resp = UrlFetchApp.fetch(url, {
    headers: {
      'User-Agent': CFG.NWS_USER_AGENT,
      'Accept': 'application/geo+json',
    },
    muteHttpExceptions: true,
  });

  const code = resp.getResponseCode();
  const text = resp.getContentText();
  if (code < 200 || code >= 300) throw new Error(`NWS request failed (${code}): ${text}`);
  return JSON.parse(text);
}

/*************************************************************
 * Weekly sheet helpers (Nest logger)
 *************************************************************/
function getIsoWeekId_(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);

  const isoYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const week = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);

  return { isoYear, week };
}

function getWeeklySheetName_(now) {
  const { isoYear, week } = getIsoWeekId_(now);
  return `oil_usage_${isoYear}_${String(week).padStart(2, '0')}`;
}

function getOrCreateWeeklySheet_(ss, now) {
  const name = getWeeklySheetName_(now);
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);

  const headers = [
    'timestamp','date','hvac_status','mode',
    'ambient_F','setpoint_F','humidity_%','outdoor_F',
    'delta_in_out_F','heating_helper',
    'stove_C','stove_F','stove_fault','stove_age_s'
  ];

  sh.getRange(1, 1, 1, headers.length).setValues([headers]);
  sh.getRange('A:A').setNumberFormat('m/d/yyyy h:mm:ss');
  sh.getRange('B:B').setNumberFormat('m/d/yyyy');

  return sh;
}

function getNextLogRow_(sh) {
  const lastRow = sh.getRange(sh.getMaxRows(), 1)
    .getNextDataCell(SpreadsheetApp.Direction.UP)
    .getRow();
  return Math.max(lastRow + 1, 2);
}

/*************************************************************
 * Nest logger (5-min trigger)
 *************************************************************/
function logNestRow() {
  const now = new Date();
  const dateOnly = new Date(now);
  dateOnly.setHours(0, 0, 0, 0);

  const ss = SpreadsheetApp.openById(CFG.SPREADSHEET_ID);
  const sh = getOrCreateWeeklySheet_(ss, now);

  const deviceName = UP.getProperty('NEST_DEVICE_NAME');
  if (!deviceName) throw new Error('Set NEST_DEVICE_NAME first (run setDeviceName()).');

  const data = sdmGet_('/' + deviceName);
  const traits = data.traits || {};

  const hvacStatus = traits['sdm.devices.traits.ThermostatHvac']?.status || 'UNKNOWN';
  const mode = traits['sdm.devices.traits.ThermostatMode']?.mode || '';
  const humidity = traits['sdm.devices.traits.Humidity']?.ambientHumidityPercent ?? '';

  const ambientC = traits['sdm.devices.traits.Temperature']?.ambientTemperatureCelsius;
  const setpointC = traits['sdm.devices.traits.ThermostatTemperatureSetpoint']?.heatCelsius;

  const ambientF = (typeof ambientC === 'number') ? Math.round(ambientC * 9/5 + 32) : '';
  const setpointF = (typeof setpointC === 'number') ? Math.round(setpointC * 9/5 + 32) : '';

  let outdoorF = '';
  try { outdoorF = getLisbonOutdoorTempF_(); } catch (e) { outdoorF = ''; }

  const deltaInOutF =
    (typeof ambientF === 'number' && typeof outdoorF === 'number')
      ? (ambientF - outdoorF)
      : '';

  const heatingHelper = (hvacStatus === 'HEATING') ? 80 : 0;

  const latest = getLatestThermo_();
  const nowMs = now.getTime();

  let stoveC = '', stoveF = '', stoveFault = '', stoveAgeS = '';
  if (latest && typeof latest.tc === 'number' && !Number.isNaN(latest.tc)) {
    stoveC = latest.tc;
    stoveF = Math.round(latest.tc * 9/5 + 32);
    stoveFault = latest.fault;
    stoveAgeS = Math.round((nowMs - latest.ts) / 1000);
  }

  const row = getNextLogRow_(sh);

  sh.getRange(row, 1, 1, 14).setValues([[
    now, dateOnly, hvacStatus, mode,
    ambientF, setpointF, humidity, outdoorF,
    deltaInOutF, heatingHelper,
    stoveC, stoveF, stoveFault, stoveAgeS
  ]]);
}

function create5MinTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction && t.getHandlerFunction() === 'logNestRow')
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('logNestRow')
    .timeBased()
    .everyMinutes(5)
    .create();

  Logger.log('Created 5-minute trigger for logNestRow().');
}

/*************************************************************
 * Stove Watch sheets + API for sidebar
 *************************************************************/
function stoveSetup() {
  const ss = SpreadsheetApp.openById(CFG.SPREADSHEET_ID);
  stoveEnsureWatchSheet_(ss);
  stoveEnsureEventsSheet_(ss);
  return { ok: true };
}

function stoveEnsureWatchSheet_(ss) {
  let sh = ss.getSheetByName(STOVE.WATCH_SHEET);
  if (!sh) sh = ss.insertSheet(STOVE.WATCH_SHEET);

  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, 6).setValues([[
      'timestamp','stove_F','stove_C','fault','age_s','cj_F'
    ]]);
    sh.getRange('A:A').setNumberFormat('m/d/yyyy h:mm:ss');
    sh.getRange('B:C').setNumberFormat('0.0');
    sh.getRange('D:E').setNumberFormat('0');
    sh.getRange('F:F').setNumberFormat('0.0');
  }
  return sh;
}

function stoveEnsureEventsSheet_(ss) {
  let sh = ss.getSheetByName(STOVE.EVENTS_SHEET);
  if (!sh) sh = ss.insertSheet(STOVE.EVENTS_SHEET);

  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, 6).setValues([[
      'timestamp','event','recommendation','stove_F','rate_F_per_min','note'
    ]]);
    sh.getRange('A:A').setNumberFormat('m/d/yyyy h:mm:ss');
    sh.getRange('D:E').setNumberFormat('0.0');
  }
  return sh;
}

function stoveGetLatestSample() {
  const raw = SP.getProperty(CFG.THERMO_LATEST_KEY);
  if (!raw) return { ok: false, message: 'No thermocouple data received yet.' };

  let sample;
  try { sample = JSON.parse(raw); } catch (e) {
    return { ok: false, message: 'THERMO_LATEST was not valid JSON.' };
  }

  const tsMs = Number(sample.ts);
  const tcC = Number(sample.tc);
  const cjC = Number(sample.cj);
  const fault = Number(sample.fault);

  if (!Number.isFinite(tsMs) || !Number.isFinite(tcC) || !Number.isFinite(fault)) {
    return { ok: false, message: 'Latest sample missing numeric fields.' };
  }

  const ageS = Math.round((Date.now() - tsMs) / 1000);
  const tcF = Math.round((tcC * 9/5 + 32) * 10) / 10;
  const cjF = Number.isFinite(cjC) ? (Math.round((cjC * 9/5 + 32) * 10) / 10) : '';

  return { ok: true, ts_ms: tsMs, stove_F: tcF, stove_C: tcC, cj_F: cjF, fault, age_s: ageS };
}

function stoveWatchAppendLatest() {
  const ss = SpreadsheetApp.openById(CFG.SPREADSHEET_ID);
  const sh = stoveEnsureWatchSheet_(ss);

  const latest = stoveGetLatestSample();
  if (!latest.ok) return latest;

  sh.appendRow([new Date(latest.ts_ms), latest.stove_F, latest.stove_C, latest.fault, latest.age_s, latest.cj_F]);
  return latest;
}

function stoveWatchClear() {
  const ss = SpreadsheetApp.openById(CFG.SPREADSHEET_ID);
  const sh = stoveEnsureWatchSheet_(ss);
  sh.clearContents();
  sh.getRange(1, 1, 1, 6).setValues([[
    'timestamp','stove_F','stove_C','fault','age_s','cj_F'
  ]]);
  return { ok: true };
}

/**
 * Optional: log simple events (e.g., LOAD) to stove_events
 * Your simplified HTML can call this on "Mark Load"
 */
function stoveLogEvent(eventName, rec, stoveF, rateFPerMin, note) {
  const ss = SpreadsheetApp.openById(CFG.SPREADSHEET_ID);
  const sh = stoveEnsureEventsSheet_(ss);

  sh.appendRow([
    new Date(),
    String(eventName || ''),
    String(rec || ''),
    numOrBlank_(stoveF),
    numOrBlank_(rateFPerMin),
    String(note || ''),
  ]);

  return { ok: true };
}

function numOrBlank_(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : '';
}