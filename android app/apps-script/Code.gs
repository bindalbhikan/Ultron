// Ultron Phone SMS web app (bound to the "Phone OTP Sheet 2026" spreadsheet).
//
// Every SMS the phone sends lands on the SMS tab. A courier's returns / pickup SMS is also worked at
// once (returns()):
//   - its OTP goes into the team's Daily OTP sheet, one row per portal (Ajio_Shadowfax, Nykaa_Delivery,
//     ...), with the count of that portal's shipments. A resent OTP for the same shipments (same AWBs,
//     or for an SMS without a POD the same courier, portal and status that day) replaces the earlier
//     code and count in its row: never a second row, never a double count;
//   - its POD (the PDF behind the SMS link, downloaded and read by the phone, as links expire) is saved
//     in Drive AGENT WORK/RETURN PODS/<yyyy-mm-dd>/, and its AWBs, each with its portal, go to the
//     RETURN PODS MASTER sheet in that folder. One POD can hold several portals (Delhivery "Client:"
//     sections, Shadowfax's Client Name column): each portal gets its own OTP row and count;
//   - the SMS tab's last column (OTP SHEET) is a checkbox, ticked once its OTP is in the Daily OTP sheet.
// Myntra's own Ekart codes (Seller MYE / MYS) are left to the Myntra OTP bot, which reads them per
// account from the portal. OTP rows are written only for SMS of the last OTP_DAYS days, so an import
// of old SMS fills the POD master and folder without old rows in the team's sheet.
// rework=1 (scripts/phone/rework_sms.py): an SMS already on the SMS tab worked again, with its POD.

const SHEET_NAME = 'SMS';
const HEADERS = ['Received At', 'From', 'Message', 'Device Time', 'SIM', 'Agent', 'OTP SHEET'];
const DEDUPE_LOOKBACK = 50;

const OTP_SHEET_ID = '1dKfym74siyYHPM-JgisDq_2LcOckiqod59aibOAHbAA';   // Daily OTP 2026
const AGENT_WORK_ID = '1uO-aOha_QKkI3f19EA7sweYPgkjMukZI';            // Drive BINDAL EXPORTS/AGENT WORK
const POD_FOLDER = 'RETURN PODS';
const POD_MASTER = 'RETURN PODS MASTER';
const POD_TAB = 'PODS';
const POD_HEADERS = ['DATE', 'PORTAL', 'COURIER', 'AWB', 'OTP', 'STATUS', 'TYPE', 'AWB STATUS', 'TIME', 'REF', 'POD FILE'];
const P = { day: 0, portal: 1, awb: 3, ref: 9 };                      // POD_HEADERS columns used to match
const LOG_TAB = 'OTP LOG';
const LOG_HEADERS = ['REF', 'DATE', 'PORTAL', 'STATUS', 'OTP', 'COUNT', 'SMS TIME', 'UPDATED'];
const OTP_NAME = 'Agent';
const OTP_DAYS = 2;
const TZ = 'Asia/Kolkata';

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
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
    let row = p.rework === '1' ? findRow(sheet, from, body, deviceTime) : 0;

    if (!row) {
      if (isDuplicate(sheet, from, body, deviceTime)) {
        return respond('duplicate');
      }
      sheet.appendRow([new Date(), asText(from), asText(body), asText(deviceTime), asText(sim)]);
      row = sheet.getLastRow();
    }
    let done = { note: '', filled: null };
    try {
      done = returns(from, body, deviceTime, p);
    } catch (err) {
      done.note = 'error: ' + err.message;
    }
    if (done.note) sheet.getRange(row, 6).setValue(done.note);
    if (done.filled !== null) sheet.getRange(row, 7).insertCheckboxes().setValue(done.filled);
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
  } else if (sheet.getRange(1, HEADERS.length).getValue() !== HEADERS[HEADERS.length - 1]) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);   // a sheet from before the Agent columns
  }
  return sheet;
}

// The SMS tab row of this SMS (1-based), or 0.
function findRow(sheet, from, body, deviceTime) {
  const last = sheet.getLastRow();
  if (last < 2) return 0;
  const rows = sheet.getRange(2, 2, last - 1, 3).getDisplayValues();
  const i = rows.findIndex(r => r[0] === from && r[1] === body && r[2] === deviceTime);
  return i < 0 ? 0 : i + 2;
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

// ------------------------------------------------------------------ returns OTP + POD

// What a courier SMS says: {courier, status, otp, count, seller, pod} or null for any other SMS.
// pod = the SMS carries a POD / shipment list link.
function parseSms(from, body) {
  const code = from.toUpperCase().replace(/^[A-Z]{2}-/, '').replace(/-[A-Z]$/, '');
  const num = (re) => { const m = body.match(re); return m ? m[1] : ''; };
  if (/DLHVRY/.test(code)) {
    const count = num(/Delivered count:\s*(\d+)/i);
    if (/Share OTP/i.test(body)) return { courier: 'Delhivery', status: 'RETURN', otp: num(/Share OTP:?\s*(\d+)/i), count, pod: true };
    if (/POD of Final Delivery/i.test(body)) return { courier: 'Delhivery', status: 'RETURN', otp: '', count, pod: true };
    if (/provide (\d+) code to the FE/i.test(body)) return { courier: 'Delhivery', status: 'PICKUP', otp: num(/provide (\d+) code/i), count: '', pod: false };
    return null;
  }
  if (/SFX/.test(code)) {
    const count = num(/Your (\d+) shipment/i) || num(/for (\d+) shipment/i);
    // "Delivery Code 5371" or "5614 is your Delivery Code for 13 shipments"
    const code = num(/(\d{4,6}) is your Delivery Code/i) || num(/Delivery Code:?\s*(\d+)/i);
    if (/Delivery Code/i.test(body)) return { courier: 'Shadowfax', status: 'RETURN', otp: code, count, pod: true };
    if (/Proof of Pickup/i.test(body)) return { courier: 'Shadowfax', status: 'PICKUP', otp: '', count, pod: true };
    return null;
  }
  if (/EKART/.test(code)) {
    const m = body.match(/OTP (\d+) .*Seller (\w+).*for (PICKUP|RETURN)/i);
    return m ? { courier: 'Ekart', status: m[3].toUpperCase(), otp: m[1], count: '', seller: m[2].toUpperCase(), pod: false } : null;
  }
  if (/XPBEES/.test(code)) {
    if (/return attempted/i.test(body)) return { courier: 'Xpressbees', status: 'RETURN', otp: '', count: num(/Acc:\s*(\d+)/i), pod: true };
    const otp = num(/OTP:?\s*(\d+)/i);
    // "attempted your pickup request ... share OTP": Xpressbees bringing returns to us (reverse pickup) - RETURN
    return otp ? { courier: 'Xpressbees', status: 'RETURN', otp, count: '', pod: /https?:\/\//.test(body) } : null;
  }
  return null;
}

const PORTALS = [[/AJIO/i, 'Ajio'], [/NYKAA/i, 'Nykaa'], [/MEESHO/i, 'Meesho'], [/MYNTRA/i, 'Myntra'],
                 [/FLIPKART/i, 'Flipkart']];
const EKART_SELLERS = { NKF: 'Nykaa', MYE: 'Myntra', MYS: 'Myntra' };
const COURIER_LABEL = { Delhivery: 'Delivery', Shadowfax: 'Shadowfax', Xpressbees: 'Xpressbees', Ekart: 'Ekart' };

function portalOf(client) {
  for (const [re, name] of PORTALS) if (re.test(client)) return name;
  const c = String(client || '').trim();
  return c ? c.charAt(0).toUpperCase() + c.slice(1).toLowerCase() : 'Unknown';
}

// The team's sheet name of a portal's courier: Ajio_Shadowfax, Nykaa_Delivery; Flipkart alone.
function sheetPortal(portal, courier) {
  return portal === 'Flipkart' ? 'Flipkart' : portal + '_' + (COURIER_LABEL[courier] || courier);
}

// The POD's shipments: {dispatch, awbs: [{awb, type, status, portal}]}, read from the text of the PDF.
function parsePod(text) {
  const out = { dispatch: '', awbs: [] };
  if (!text) return out;
  const d = text.match(/Dispatch ID\s*(\d+)/i);
  if (d) out.dispatch = d[1];
  if (/AWB\s*:\s*\d/i.test(text)) {                              // Xpressbees: "Client : X", "AWB : n" blocks
    const client = (text.match(/Client\s*:\s*([^\n]+)/i) || [, ''])[1].trim();
    for (const block of text.split(/AWB\s*:\s*/i).slice(1)) {
      const awb = (block.match(/^(\d+)/) || [, ''])[1];
      if (!awb) continue;
      const type = (block.match(/\b(DTO|RTO|FWD)\b/) || [, ''])[1];
      const status = (block.match(/\b(Undelivered|Delivered|Rejected)\b/i) || [, ''])[1].toUpperCase();
      out.awbs.push({ awb, type, status: status === 'UNDELIVERED' ? 'REJECTED' : status, portal: portalOf(client) });
    }
    if (out.awbs.length) return out;
  }
  if (/Client:/i.test(text)) {                                   // Delhivery: "Client: X" sections
    const parts = text.split(/Client:\s*/i).slice(1);
    for (const part of parts) {
      const client = part.split('\n')[0].trim();
      const re = /(\d{10,16})\s+([A-Z]{2,4})\s+(ACCEPTED|REJECTED|PENDING)/g;
      let m;
      while ((m = re.exec(part))) out.awbs.push({ awb: m[1], type: m[2], status: m[3], portal: portalOf(client) });
    }
    return out;
  }
  const t = text.split(/\s+/).filter(Boolean);                   // Shadowfax: Sr / AWB / COID / Client Name
  const isHead = (i) => /^Client$/i.test(t[i] || '') && /^Name$/i.test(t[i + 1] || '');
  const head = t.findIndex((w, i) => isHead(i));
  if (head >= 0) {
    const isAwb = (w) => /^[A-Z0-9]{8,24}$/i.test(w || '') && /\d/.test(w);
    const ends = (j, n) => (t[j] === String(n + 1) && isAwb(t[j + 1])) || /^Following$/i.test(t[j])
      || (/^Sr$/i.test(t[j]) && /^No/i.test(t[j + 1] || '')) || isHead(j);
    let i = head + 2, n = 1;
    while (i < t.length) {
      if (isHead(i)) { i += 2; n = 1; continue; }           // the next seller account's table
      if (t[i] !== String(n) || !isAwb(t[i + 1])) { i++; continue; }
      const awb = t[i + 1];
      let j = i + 3;
      const client = [];
      while (j < t.length && !ends(j, n)) client.push(t[j++]);
      out.awbs.push({ awb, type: '', status: 'DELIVERED', portal: portalOf(client.join(' ')) });
      i = j;
      n++;
    }
    if (out.awbs.length) return out;
  }
  for (const [re, name] of PORTALS) {                            // anything else: the portals it names
    const hits = (text.match(new RegExp(re.source, 'gi')) || []).length;
    if (hits) out.awbs.push({ awb: '', type: '', status: '', portal: name, hits });
  }
  return out;
}

// The text of an HTML page, one cell / line per line (scripts and styles dropped).
function htmlText(html) {
  return html.replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, '')
    .replace(/<br\s*\/?>|<\/(p|div|tr|li|h\d|td|th)>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/&quot;/g, '"')
    .replace(/[ \t]*\n[ \t\n]*/g, '\n');
}

// Works one SMS: {note for the SMS tab's Agent column ('' = not a courier SMS), filled: whether its
// OTP is in the Daily OTP sheet (null = the SMS has no OTP)}.
function returns(from, body, deviceTime, p) {
  const sms = parseSms(from, body);
  if (!sms) return { note: '', filled: null };

  const when = deviceTime ? new Date(deviceTime.replace(' ', 'T') + '+05:30') : new Date();
  const day = Utilities.formatDate(when, TZ, 'dd-MM-yyyy');
  const time = Utilities.formatDate(when, TZ, 'HH:mm');
  const otpSheet = sms.otp ? SpreadsheetApp.openById(OTP_SHEET_ID).getSheets()[0] : null;
  const otpRows = otpSheet && otpSheet.getLastRow() > 1 ? otpSheet.getRange(2, 1, otpSheet.getLastRow() - 1, 6).getDisplayValues() : [];
  if (sms.courier === 'Ekart' && EKART_SELLERS[sms.seller] === 'Myntra') {
    return { note: 'Myntra Ekart: left to the Myntra OTP bot', filled: otpRows.some(r => r[0] === day && r[3] === sms.otp) };
  }
  let html = '';
  if (p.html) {
    html = Utilities.newBlob(Utilities.base64Decode(p.html)).getDataAsString('UTF-8');
    if (!p.pdftext) p.pdftext = htmlText(html);
  }
  const pod = parsePod(p.pdftext || '');
  const notes = [];

  // the shipments by portal
  const groups = {};
  const named = pod.awbs.filter(a => a.awb);
  if (named.length) {
    named.forEach(a => (groups[a.portal] = groups[a.portal] || []).push(a));
  } else if (pod.awbs.length) {
    const top = pod.awbs.sort((a, b) => b.hits - a.hits)[0];
    groups[top.portal] = [];
  } else {
    const portal = sms.courier === 'Ekart' ? (EKART_SELLERS[sms.seller] || 'Ekart ' + sms.seller) : 'Unknown';
    groups[portal] = [];
  }

  // the POD into Drive AGENT WORK/RETURN PODS/<date>/
  let file = '';
  if (p.pdf || html) {
    const portals = Object.keys(groups).join(' + ');
    const name = Utilities.formatDate(when, TZ, 'HH-mm') + ' ' + sms.courier + ' ' + portals + ' ' + sms.status +
                 (sms.otp ? ' OTP ' + sms.otp : ' POD') + '.pdf';
    const folder = podFolder(Utilities.formatDate(when, TZ, 'yyyy-MM-dd'));
    const have = folder.getFilesByName(name);                     // a reworked SMS: its POD once
    const blob = p.pdf ? Utilities.newBlob(Utilities.base64Decode(p.pdf), 'application/pdf', name)
      : Utilities.newBlob(html, 'text/html', name).getAs('application/pdf').setName(name);
    file = (have.hasNext() ? have.next() : folder.createFile(blob)).getUrl();
    notes.push('POD saved');
  } else if (sms.pod) {
    notes.push('POD not downloaded' + (p.pdferror ? ' (' + p.pdferror + ')' : ''));
  }

  const podTab = master();
  const logTab = tab(SpreadsheetApp.getActive(), LOG_TAB, LOG_HEADERS);
  const podRows = podTab.getLastRow() > 1 ? podTab.getRange(2, 1, podTab.getLastRow() - 1, POD_HEADERS.length).getDisplayValues() : [];
  const logRows = logTab.getLastRow() > 1 ? logTab.getRange(2, 1, logTab.getLastRow() - 1, LOG_HEADERS.length).getDisplayValues() : [];
  const fresh = (Date.now() - when.getTime()) <= OTP_DAYS * 86400000;
  let filled = sms.otp ? true : null;

  for (const portal of Object.keys(groups)) {
    const awbs = groups[portal];
    const sp = sheetPortal(portal, sms.courier);
    const myntra = portal === 'Myntra';                         // Myntra's codes: the Myntra OTP bot's rows
    const count = awbs.length ? String(awbs.filter(a => a.status !== 'REJECTED').length) : String(sms.count || '');

    // the same shipments seen before (a resent OTP, or the final POD of a dispatch): its REF
    const ids = new Set(awbs.map(a => a.awb));
    const seen = ids.size ? podRows.find(r => r[P.day] === day && r[P.portal] === portal && ids.has(r[P.awb])) : null;
    const ref = seen ? seen[P.ref]
      : ids.size ? [sms.courier, pod.dispatch || time, portal, sms.status].join('|')
      : [sms.courier, portal, sms.status, day].join('|');
    const logged = logRows.find(r => r[0] === ref);
    // a code older than the one already filed for these shipments (a rework): changes nothing filed.
    // SMS TIME is the time of the filed code's SMS (a final POD after it carries no code).
    const older = !!(sms.otp && logged && logged[6] && deviceTime && deviceTime < logged[6]);
    const otp = older ? logged[4] : sms.otp || (logged ? logged[4] : '');

    if (older) {
      notes.push(sp + ': a later code (' + logged[4] + ') is filed');
      if (sms.otp && !otpRows.some(r => r[0] === day && r[1] === sp && r[3] === logged[4])) filled = false;
      if (!podRows.some(r => r[P.ref] === ref) && awbs.length) {
        const rows = awbs.map(a => [day, portal, sms.courier, a.awb, otp, sms.status, a.type, a.status, time, ref, file]);
        podTab.getRange(podTab.getLastRow() + 1, 1, rows.length, POD_HEADERS.length).setValues(rows.map(r => r.map(asText)));
        rows.forEach(r => podRows.push(r.map(String)));
      }
      continue;
    }
    if (sms.otp && myntra) {
      notes.push(sp + ': left to the Myntra OTP bot');
      if (!otpRows.some(r => r[0] === day && r[3] === sms.otp)) filled = false;
    } else if (sms.otp) {
      const put = putOtp(otpSheet, otpRows, day, sp, sms.status, otp, count, logged, fresh);
      notes.push(sp + ' ' + count + ' OTP ' + otp + ': ' + put);
      if (put === 'not in the sheet') filled = false;
    } else if (logged && logged[4] && count && fresh && !myntra) {   // final POD: the count only
      const sheet = SpreadsheetApp.openById(OTP_SHEET_ID).getSheets()[0];
      const rows = sheet.getLastRow() > 1 ? sheet.getRange(2, 1, sheet.getLastRow() - 1, 6).getDisplayValues() : [];
      putOtp(sheet, rows, day, sp, sms.status, logged[4], count, logged, true);
    }
    const entry = [ref, day, sp, sms.status, otp, count, sms.otp ? deviceTime : (logged ? logged[6] : ''), new Date()];
    if (logged) {
      logTab.getRange(logRows.indexOf(logged) + 2, 1, 1, entry.length).setValues([entry.map(asText)]);
      logged.splice(0, entry.length, ...entry.map(String));
    } else {
      logTab.appendRow(entry.map(asText));
      logRows.push(entry.map(String));
    }

    // the AWBs of this REF, replaced by this POD's
    if (awbs.length) {
      for (let i = podRows.length - 1; i >= 0; i--) {
        if (podRows[i][P.ref] === ref) { podTab.deleteRow(i + 2); podRows.splice(i, 1); }
      }
      const rows = awbs.map(a => [day, portal, sms.courier, a.awb, otp, sms.status, a.type, a.status, time, ref, file]);
      podTab.getRange(podTab.getLastRow() + 1, 1, rows.length, POD_HEADERS.length).setValues(rows.map(r => r.map(asText)));
      rows.forEach(r => podRows.push(r.map(String)));
    }
  }
  return { note: notes.join('; ') || 'worked', filled };
}

// One OTP row of the team's sheet: the row of the earlier code of this REF updated (a resend), a row
// the team already wrote left alone, else a new row. Older SMS (write = false) are only looked up.
function putOtp(sheet, rows, day, portal, status, otp, count, logged, write) {
  const at = (code) => rows.findIndex(r => r[0] === day && r[1] === portal && r[3] === code && r[4].toUpperCase() === status);
  const old = logged && logged[4] ? at(logged[4]) : -1;
  if (old >= 0 && write) {
    const team = rows.findIndex((r, i) => i !== old && r[0] === day && r[1] === portal && r[3] === otp && r[4].toUpperCase() === status);
    if (team >= 0 && rows[old][5] === OTP_NAME) {                // the team already wrote the new code: ours goes
      sheet.deleteRow(old + 2);
      rows.splice(old, 1);
      return 'resent, ' + otp + ' already in the sheet (removed our ' + logged[4] + ')';
    }
    if (rows[old][5] !== OTP_NAME) {                              // a row the team wrote: never changed
      return logged[4] === otp ? 'already in the sheet' : 'resent ' + otp + ': not written, the team\'s row has ' + logged[4];
    }
    sheet.getRange(old + 2, 3, 1, 2).setValues([[count, otp]]);
    rows[old][2] = count;
    rows[old][3] = otp;
    return logged[4] === otp ? 'count updated' : 'resent, replaced ' + logged[4];
  }
  // the team's own row of this code (their portal name may differ); the agent's rows of other portals
  // with the same code (one POD, several portals) do not count
  if (at(otp) >= 0 || rows.some(r => r[0] === day && r[3] === otp && r[5] !== OTP_NAME)) return 'already in the sheet';
  if (!write) return 'not in the sheet';
  sheet.appendRow([day, portal, count, otp, status, OTP_NAME, '']);
  rows.push([day, portal, count, otp, status, OTP_NAME]);
  return 'added';
}

// The RETURN PODS MASTER sheet in Drive AGENT WORK/RETURN PODS (made on first use).
function master() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('POD_MASTER_ID');
  if (!id) {
    const folder = podFolder('');
    const found = folder.getFilesByName(POD_MASTER);
    if (found.hasNext()) {
      id = found.next().getId();
    } else {
      const ss = SpreadsheetApp.create(POD_MASTER);
      DriveApp.getFileById(ss.getId()).moveTo(folder);
      ss.getSheets()[0].setName(POD_TAB);
      id = ss.getId();
    }
    props.setProperty('POD_MASTER_ID', id);
  }
  return tab(SpreadsheetApp.openById(id), POD_TAB, POD_HEADERS);
}

function tab(ss, name, headers) {
  let sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  if (sheet.getLastRow() === 0) {                                // new, or the first tab of a new spreadsheet
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function podFolder(day) {
  const sub = (parent, name) => {
    const it = parent.getFoldersByName(name);
    return it.hasNext() ? it.next() : parent.createFolder(name);
  };
  const pods = sub(DriveApp.getFolderById(AGENT_WORK_ID), POD_FOLDER);
  return day ? sub(pods, day) : pods;
}

// Run once from the editor after putting your own key below.
function setupSecret() {
  PropertiesService.getScriptProperties().setProperty('SECRET', 'put-your-long-random-key-here');
}

// Run once from the editor after an update: asks for the new permissions (the Daily OTP sheet, Drive).
function authorize() {
  master();
  SpreadsheetApp.openById(OTP_SHEET_ID).getName();
  podFolder(Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd'));   // creates folders: the full Drive permission
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
