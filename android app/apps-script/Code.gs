const SHEET_NAME = 'SMS';
const HEADERS = ['Received At', 'From', 'Message', 'Device Time', 'SIM'];
const DEDUPE_LOOKBACK = 50;

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const p = (e && e.parameter) || {};
    const secret = PropertiesService.getScriptProperties().getProperty('SECRET');

    if (!secret || p.key !== secret) {
      return respond('unauthorized');
    }

    const from = (p.from || '').trim();
    const body = (p.body || '').trim();
    const deviceTime = (p.time || '').trim();
    const sim = (p.sim || '').trim();   // "SIM 1" / "SIM 2" (Ultron Phone 2.0+)

    if (!body) {
      return respond('empty');
    }

    const sheet = getSheet();

    if (isDuplicate(sheet, from, body, deviceTime)) {
      return respond('duplicate');
    }

    sheet.appendRow([new Date(), asText(from), asText(body), asText(deviceTime), asText(sim)]);
    return respond('ok');
  } catch (err) {
    return respond('error: ' + err.message);
  } finally {
    lock.releaseLock();
  }
}

function getSheet() {
  const ss = SpreadsheetApp.getActive();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

// Skips a row only when sender, message and device time all match a recent row,
// so retries never create duplicates but two genuine identical SMS still get logged.
function isDuplicate(sheet, from, body, deviceTime) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;
  const start = Math.max(2, lastRow - DEDUPE_LOOKBACK + 1);
  const rows = sheet.getRange(start, 2, lastRow - start + 1, 3).getDisplayValues();
  return rows.some(r => r[0] === from && r[1] === body && r[2] === deviceTime);
}

// Leading apostrophe keeps values as plain text: phone numbers stay intact,
// dates are not reformatted, and messages starting with "=" are never run as formulas.
function asText(value) {
  return value ? "'" + value : '';
}

function respond(text) {
  return ContentService.createTextOutput(text);
}

// Run once from the editor after putting your own key below.
function setupSecret() {
  PropertiesService.getScriptProperties().setProperty('SECRET', 'put-your-long-random-key-here');
}

function testInsert() {
  const result = doPost({
    parameter: {
      key: PropertiesService.getScriptProperties().getProperty('SECRET'),
      from: 'TEST-SENDER',
      body: 'Hello from testInsert ' + new Date().toISOString(),
      time: Utilities.formatDate(new Date(), 'Asia/Kolkata', 'yyyy-MM-dd HH:mm:ss')
    }
  });
  Logger.log(result.getContent());
}
