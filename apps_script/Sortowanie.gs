// Sortuje zakładkę Oferty od razu po zmianie Statusu / Aktywnej / Wysłano CV.
// Kolejność jak w sheets.py (sort_rank): wysłane > rozważam > reszta > nieaktywne > odrzucone.
// Wklej: Rozszerzenia > Apps Script > wklej całość > Zapisz > Uruchom raz sortujOferty (zgoda na uprawnienia) > dodaj wyzwalacz
// "Z arkusza > Przy edycji" dla funkcji przyEdycji (zwykły onEdit też zadziała, ale ten bywa niezawodniejszy).
var REJECTED = ['Odrzucone', 'Rezygnacja', 'Ghosting'];
var IN_PROCESS = ['Wysłane', 'Odpowiedź', 'Rozmowa', 'Zadanie domowe', 'Oferta', 'Przyjęta'];
var CONSIDER = ['Do rozważenia', 'Rozważam'];

function rank_(firma, stanowisko, status, aktywna) {
  if (!String(firma).trim() && !String(stanowisko).trim()) return 9;
  status = String(status).trim();
  if (REJECTED.indexOf(status) >= 0) return 4;
  if (String(aktywna).trim() === 'Nie') return 3;
  if (IN_PROCESS.indexOf(status) >= 0) return 0;
  if (CONSIDER.indexOf(status) >= 0) return 1;
  return 2;
}

function sortujOferty() {
  var sh = SpreadsheetApp.getActive().getSheetByName('Oferty');
  var last = sh.getLastRow(), cols = sh.getLastColumn();
  if (last < 2) return;
  var head = sh.getRange(1, 1, 1, cols).getValues()[0];
  var c = function (n) { return head.indexOf(n); };
  var data = sh.getRange(2, 1, last - 1, cols).getValues();
  var ranks = data.map(function (r) { return [rank_(r[c('Firma')], r[c('Stanowisko')], r[c('Status')], r[c('Aktywna')])]; });
  var helper = cols + 1;
  sh.getRange(2, helper, last - 1, 1).setValues(ranks);
  sh.getRange(2, 1, last - 1, helper).sort([
    {column: helper, ascending: true},
    {column: c('Wysłano CV') + 1, ascending: false},
    {column: c('Match') + 1, ascending: false}]);
  sh.deleteColumn(helper);
}

function przyEdycji(e) {
  var sh = e.range.getSheet();
  if (sh.getName() !== 'Oferty' || e.range.getRow() < 2) return;
  var name = sh.getRange(1, e.range.getColumn()).getValue();
  if (['Status', 'Aktywna', 'Wysłano CV'].indexOf(name) >= 0) sortujOferty();
}
