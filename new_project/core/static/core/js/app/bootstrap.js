// Bootstrap файла Stimulus-приложения для core.
// Ожидается, что UMD-скрипт Stimulus уже загружен в base.html
// и предоставляет глобальный объект Stimulus.

(function () {
  if (typeof Stimulus === "undefined") {
    // Если Stimulus не доступен, выходим, чтобы не падать.
    console.error(
      "Stimulus global is not available. Make sure the UMD script is loaded before bootstrap.js."
    );
    return;
  }

  // Создаем (или переиспользуем) единое приложение Stimulus.
  window.stimulusApp = window.stimulusApp || Stimulus.Application.start();
})();

