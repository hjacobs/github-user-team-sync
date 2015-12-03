/*
 * Return second and third columns from form responses (first column is timestamp)
 */
function getGitHubUsernames() {
  var spreadsheet = SpreadsheetApp.openByUrl('https://docs.google.com/spreadsheets/d/XXXEXAMPLEXXX')
  var sheet = spreadsheet.getSheetByName('Form Responses 1')
  var rows = sheet.getSheetValues(1, 2, sheet.getLastRow(), 2);
  return rows;
}
