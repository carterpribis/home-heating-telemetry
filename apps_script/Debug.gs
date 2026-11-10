function debugThermoLatest() {
  const raw = PropertiesService.getScriptProperties().getProperty(CFG.THERMO_LATEST_KEY);
  Logger.log(raw);
  if (raw) {
    const j = JSON.parse(raw);
    Logger.log("age_s=" + Math.round((Date.now() - Number(j.ts)) / 1000));
  }
}