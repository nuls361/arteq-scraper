import { useState, useEffect, useCallback, useRef } from "react";

const SUPABASE_URL = "https://dgrbbvdvziwcxqlyccng.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRncmJidmR2eml3Y3hxbHljY25nIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI0OTk0NTcsImV4cCI6MjA4ODA3NTQ1N30.d9NhDhiZz6MtYwmPcCI2n8ASnw3wNP-dmb2fyFJoqXU";

async function supaFetch(table, params = "") {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${params}`, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

async function supaPost(table, data) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}


const TIER = {
  hot:    { label: "Hot",    bg: "#FDECEC", color: "#C13030", dot: "#E5484D" },
  warm:   { label: "Warm",   bg: "#FFF0E1", color: "#AD5700", dot: "#F5A623" },
  parked: { label: "Parked", bg: "#F2F3F5", color: "#6B6F76", dot: "#A0A3A9" },
  disqualified: { label: "DQ", bg: "#F2F3F5", color: "#A0A3A9", dot: "#A0A3A9" },
};
const ENG = {
  fractional:  { label: "Fractional",  bg: "#EDE9FE", color: "#6D28D9" },
  interim:     { label: "Interim",     bg: "#DBEAFE", color: "#1D4ED8" },
  "full-time": { label: "Full-time",   bg: "#F2F3F5", color: "#6B6F76" },
  convertible: { label: "Convertible", bg: "#D1FAE5", color: "#065F46" },
};

function TierPill({ tier }) {
  const c = TIER[tier] || TIER.parked;
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:5, padding:"3px 10px", borderRadius:4, fontSize:12, fontWeight:500, background:c.bg, color:c.color }}>
      <span style={{ width:6, height:6, borderRadius:"50%", background:c.dot }} />
      {c.label}
    </span>
  );
}

function EngPill({ type }) {
  if (!type || type === "unknown") return <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>;
  const c = ENG[type] || { label: type, bg:"#F2F3F5", color:"#6B6F76" };
  return <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:c.bg, color:c.color }}>{c.label}</span>;
}

function SourcePill({ source }) {
  if (!source) return <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>;
  return <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:"#F2F3F5", color:"#6B6F76" }}>{source}</span>;
}

function Score({ v }) {
  if (v == null) return <span style={{ color:"#A0A3A9" }}>—</span>;
  const color = v >= 70 ? "#E5484D" : v >= 40 ? "#F5A623" : "#A0A3A9";
  return <span style={{ fontWeight:600, fontSize:13, color, fontVariantNumeric:"tabular-nums" }}>{v}</span>;
}


function ColHead({ children, width, align, sk, sort, onSort }) {
  const active = sk && sort?.key === sk;
  return (
    <th onClick={() => sk && onSort(sk)} style={{
      padding:"8px 14px", fontWeight:500, fontSize:11, color:"#A0A3A9",
      textTransform:"uppercase", letterSpacing:0.4, textAlign:align||"left",
      borderBottom:"1px solid #EBEBED", width, whiteSpace:"nowrap",
      cursor:sk?"pointer":"default", userSelect:"none",
      background:"#F7F7F8", position:"sticky", top:0, zIndex:2,
    }}>
      <span style={{ display:"inline-flex", alignItems:"center", gap:3 }}>
        {children}
        {active && <span style={{ fontSize:9 }}>{sort?.dir==="asc"?"▲":"▼"}</span>}
      </span>
    </th>
  );
}


async function supaUploadFile(bucket, path, file) {
  const res = await fetch(`${SUPABASE_URL}/storage/v1/object/${bucket}/${path}`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  // Public URL for the file
  return `${SUPABASE_URL}/storage/v1/object/public/${bucket}/${path}`;
}

function formatFileSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const FILE_ICONS = {
  "application/pdf": "📄",
  "image/": "🖼",
  "text/": "📃",
  "application/vnd.openxmlformats": "📊",
  "application/vnd.ms-": "📊",
};

function fileIcon(mimeType) {
  if (!mimeType) return "📎";
  for (const [prefix, icon] of Object.entries(FILE_ICONS)) {
    if (mimeType.startsWith(prefix)) return icon;
  }
  return "📎";
}

function cleanTitle(title) {
  if (!title) return "—";
  return title
    // Remove employment type prefix
    .replace(/^(Vollzeit|Teilzeit|Full[\s-]?time|Part[\s-]?time)\s*[-–—:/|]\s*/i, "")
    // Remove trailing keyword segments after dash
    .replace(/\s*[-–—]\s*(100%\s*remote[-\s]?first|remote[-\s]?first|remote|hybrid|on[\s-]?site|startup|scale[\s-]?up|home[\s-]?office)\s*/gi, " ")
    // Remove gender tags in various formats
    .replace(/\s*\(?[mwfd]\/[mwfd](?:\/[mwfd])?\)?\s*/gi, "")
    .replace(/\s*\(all genders?\)\s*/gi, "")
    .replace(/\s*\(gn?\)\s*/gi, "")
    // Remove :in/:r German inclusive forms → keep base word
    .replace(/:in\b/g, "")
    .replace(/:r\b/g, "")
    // Collapse multiple separators
    .replace(/\s*[-–—/]\s*[-–—/]\s*/g, " / ")
    .replace(/\s+/g, " ")
    .trim()
    // Remove trailing dash or slash
    .replace(/\s*[-–—/]\s*$/, "")
    .trim();
}

function cleanLocation(loc) {
  if (!loc) return "—";
  // Deduplicate repeated city names (e.g. "Hamburg, Hamburg, Germany")
  const parts = loc.split(/[,;]\s*/);
  const seen = new Set();
  const unique = parts.filter(p => {
    const key = p.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return unique.join(", ") || "—";
}

const ENTRY_TYPE = {
  signal:       { label: "Signal",       icon: "⚡", bg: "#FDECEC", color: "#C13030" },
  news:         { label: "News",         icon: "📰", bg: "#DBEAFE", color: "#1D4ED8" },
  meeting_note: { label: "Meeting Note", icon: "🤝", bg: "#EDE9FE", color: "#6D28D9" },
  note:         { label: "Note",         icon: "📝", bg: "#FFF0E1", color: "#AD5700" },
  file:         { label: "File",         icon: "📎", bg: "#F0FDF4", color: "#15803D" },
  agent_action:      { label: "Agent",            icon: "🤖", bg: "#EDE9FE", color: "#6D28D9" },
  outreach:          { label: "Outreach",         icon: "📨", bg: "#DBEAFE", color: "#1D4ED8" },
  role_analysis:     { label: "Role Analysis",    icon: "📋", bg: "#D1FAE5", color: "#065F46" },
  role_dm_research:  { label: "Hiring Manager",   icon: "🎯", bg: "#FEF3C7", color: "#92400E" },
  contact_intel:     { label: "Contact Intel",    icon: "🧠", bg: "#DBEAFE", color: "#1D4ED8" },
  personal_hooks:    { label: "Personal Hooks",   icon: "🎣", bg: "#FEF3C7", color: "#92400E" },
  company_analysis:  { label: "Company Analysis", icon: "🏢", bg: "#D1FAE5", color: "#065F46" },
  funding_event:     { label: "Funding",          icon: "💰", bg: "#FFF0E1", color: "#AD5700" },
  outreach_history:  { label: "Outreach History", icon: "📬", bg: "#DBEAFE", color: "#1D4ED8" },
};

function OutreachThread({ thread, contacts: threadContacts }) {
  if (!thread || thread.length === 0) return null;

  const firstMsg = thread[0];
  const contactName = (() => {
    const cid = firstMsg.contact_id;
    const c = (threadContacts || []).find(tc => tc.id === cid);
    return c ? c.name : "Unknown";
  })();

  return (
    <div style={{ border:"1px solid #EBEBED", borderRadius:8, overflow:"hidden", marginBottom:12 }}>
      <div style={{ padding:"10px 14px", background:"#F0F4FF", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", gap:8 }}>
        <span style={{ fontSize:14 }}>💬</span>
        <span style={{ fontSize:12, fontWeight:600, color:"#1D4ED8" }}>Thread with {contactName}</span>
        <span style={{ flex:1 }} />
        <span style={{ fontSize:10, color:"#A0A3A9" }}>{thread.length} messages</span>
        {thread.some(m => m.reply_sentiment) && (
          <span style={{
            padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:600,
            background: thread.some(m => m.reply_sentiment === "interested" || m.reply_sentiment === "positive") ? "#D1FAE5" : "#FEF3C7",
            color: thread.some(m => m.reply_sentiment === "interested" || m.reply_sentiment === "positive") ? "#065F46" : "#92400E",
          }}>
            {thread.find(m => m.reply_sentiment)?.reply_sentiment}
          </span>
        )}
      </div>
      {thread.map((msg, i) => {
        const isOutbound = msg.direction === "outbound";
        const date = msg.created_at ? new Date(msg.created_at) : null;
        return (
          <div key={msg.id || i} style={{
            padding:"10px 14px",
            background: isOutbound ? "#fff" : "#F7F7F8",
            borderBottom: i < thread.length - 1 ? "1px solid #F0F0F2" : "none",
          }}>
            <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:4 }}>
              <span style={{ fontSize:12, fontWeight:600, color: isOutbound ? "#1D4ED8" : "#065F46" }}>
                {isOutbound ? "Niels (A-Line)" : contactName}
              </span>
              <span style={{
                padding:"1px 5px", borderRadius:3, fontSize:9, fontWeight:600,
                background: isOutbound ? "#DBEAFE" : "#D1FAE5",
                color: isOutbound ? "#1D4ED8" : "#065F46",
              }}>{isOutbound ? "sent" : "reply"}</span>
              {msg.status && msg.status === "draft" && (
                <span style={{ padding:"1px 5px", borderRadius:3, fontSize:9, fontWeight:600, background:"#FEF3C7", color:"#92400E" }}>draft</span>
              )}
              <span style={{ flex:1 }} />
              <span style={{ fontSize:10, color:"#A0A3A9" }}>
                {date ? date.toLocaleDateString("en-GB", { day:"numeric", month:"short", hour:"2-digit", minute:"2-digit" }) : ""}
              </span>
            </div>
            {msg.subject && i === 0 && (
              <div style={{ fontSize:12, fontWeight:600, color:"#1A1A1A", marginBottom:4 }}>{msg.subject}</div>
            )}
            <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.5 }}
              dangerouslySetInnerHTML={{ __html: msg.body_html || msg.raw_text || "" }}
            />
          </div>
        );
      })}
    </div>
  );
}

// ── Placeholder outreach emails (German, Lena/Niels persona) ──
const PLACEHOLDER_EMAILS_HM = [
  {
    id: "ph-1", direction: "outbound", subject: "Interim-Besetzung für Ihre offene Position",
    body_html: "<p>Hallo Herr Müller,</p><p>mein Name ist Lena, ich arbeite mit Niels bei A-Line zusammen. Wir haben gesehen, dass Sie aktuell eine Interim-CFO-Position besetzen möchten.</p><p>Wir haben mehrere erfahrene Interim-CFOs in unserem Netzwerk, die sofort verfügbar wären — darunter Profile mit Series-B-Erfahrung und IPO-Readiness.</p><p>Hätten Sie diese Woche 15 Minuten für einen kurzen Austausch?</p><p>Beste Grüße,<br/>Lena</p>",
    status: "sent", sequence_step: 1, email_opened: true, times_opened: 2, bounced: false, reply_sentiment: null,
    sent_at: "2026-02-28T09:15:00Z", thread_id: "ph-thread-1", instantly_lead_id: "il-001",
  },
  {
    id: "ph-2", direction: "outbound", subject: null,
    body_html: "<p>Hallo Herr Müller,</p><p>kurzes Follow-up zu meiner Nachricht von letzter Woche. Wir haben gerade einen Interim-CFO aus einem ähnlichen Scale-up-Umfeld (FinTech, 80 MA) erfolgreich vermittelt.</p><p>Falls das Thema noch aktuell ist — ich schicke Ihnen gerne 2-3 anonymisierte Profile.</p><p>Viele Grüße,<br/>Lena</p>",
    status: "sent", sequence_step: 2, email_opened: true, times_opened: 1, bounced: false, reply_sentiment: null,
    sent_at: "2026-03-03T08:30:00Z", thread_id: "ph-thread-1", instantly_lead_id: "il-001",
  },
  {
    id: "ph-3", direction: "inbound", subject: null,
    body_html: "<p>Hallo Lena,</p><p>danke für die Nachricht. Das Thema ist tatsächlich noch aktuell — wir tun uns schwer, die richtige Person zu finden.</p><p>Schicken Sie mir gerne die Profile, dann schaue ich mir das an.</p><p>Grüße,<br/>Thomas Müller</p>",
    status: "received", sequence_step: null, email_opened: false, times_opened: 0, bounced: false, reply_sentiment: "interested",
    sent_at: "2026-03-04T14:22:00Z", thread_id: "ph-thread-1", instantly_lead_id: "il-001",
  },
  {
    id: "ph-4", direction: "outbound", subject: null,
    body_html: "<p>Hallo Herr Müller,</p><p>freut mich! Ich habe Niels gebeten, Ihnen drei passende Profile zusammenzustellen. Sie erhalten diese morgen per Mail.</p><p>Wäre Donnerstag oder Freitag ein guter Zeitpunkt für einen kurzen Call, um die Profile zu besprechen?</p><p>Beste Grüße,<br/>Lena</p>",
    status: "sent", sequence_step: null, email_opened: false, times_opened: 0, bounced: false, reply_sentiment: null,
    sent_at: "2026-03-04T16:05:00Z", thread_id: "ph-thread-1", instantly_lead_id: "il-001",
  },
];

const PLACEHOLDER_EMAILS_AGENCY = [
  {
    id: "ph-a1", direction: "outbound", subject: "Partnerschaft: Interim & Fractional Executives",
    body_html: "<p>Hallo Frau Weber,</p><p>mein Name ist Niels von A-Line. Wir vermitteln Interim- und Fractional-Executives im DACH-Raum — vor allem CFO, COO und VP-Level.</p><p>Ich habe gesehen, dass Ihre Agentur einen starken Fokus auf Finance-Positionen hat. Wir könnten uns hier gut ergänzen — wir haben Supply, Sie haben Demand.</p><p>Hätten Sie Interesse an einem kurzen Kennenlerngespräch?</p><p>Beste Grüße,<br/>Niels</p>",
    status: "sent", sequence_step: 1, email_opened: true, times_opened: 3, bounced: false, reply_sentiment: null,
    sent_at: "2026-02-25T10:00:00Z", thread_id: "ph-thread-a1", instantly_lead_id: "il-a01",
  },
  {
    id: "ph-a2", direction: "outbound", subject: null,
    body_html: "<p>Hallo Frau Weber,</p><p>kurzes Follow-up — wir haben aktuell 12 verfügbare Interim-CFOs und 8 Fractional-COOs im Pool. Alle mit nachweisbarer Scale-up-Erfahrung.</p><p>Falls Partnerschaft interessant klingt, blocke ich gerne 20 Minuten für einen Austausch.</p><p>VG Niels</p>",
    status: "sent", sequence_step: 2, email_opened: true, times_opened: 1, bounced: false, reply_sentiment: null,
    sent_at: "2026-03-01T09:15:00Z", thread_id: "ph-thread-a1", instantly_lead_id: "il-a01",
  },
];

const PLACEHOLDER_EMAILS_CANDIDATE = [
  {
    id: "ph-c1", direction: "outbound", subject: "Spannende Interim-Mandate im DACH-Raum",
    body_html: "<p>Hallo Herr Schneider,</p><p>mein Name ist Niels von A-Line. Ihr Profil ist mir über LinkedIn aufgefallen — Ihre Erfahrung als Interim-CFO im Scale-up-Umfeld passt sehr gut zu mehreren Mandaten, die wir aktuell besetzen.</p><p>Konkret suchen wir gerade einen Interim-CFO für ein Series-B FinTech in Hamburg (6-12 Monate) sowie einen Fractional-CFO für ein HealthTech in München.</p><p>Wären Sie offen für einen kurzen Austausch?</p><p>Beste Grüße,<br/>Niels</p>",
    status: "sent", sequence_step: 1, email_opened: true, times_opened: 3, bounced: false, reply_sentiment: null,
    sent_at: "2026-02-26T08:45:00Z", thread_id: "ph-thread-c1", instantly_lead_id: "il-c01",
  },
  {
    id: "ph-c2", direction: "inbound", subject: null,
    body_html: "<p>Hallo Niels,</p><p>danke für die Nachricht. Das FinTech-Mandat in Hamburg klingt interessant — ich bin ab April verfügbar und habe bereits zwei Series-B-Unternehmen durch die Wachstumsphase begleitet.</p><p>Können wir nächste Woche telefonieren?</p><p>Grüße,<br/>Marcus Schneider</p>",
    status: "received", sequence_step: null, email_opened: false, times_opened: 0, bounced: false, reply_sentiment: "interested",
    sent_at: "2026-02-27T14:10:00Z", thread_id: "ph-thread-c1", instantly_lead_id: "il-c01",
  },
  {
    id: "ph-c3", direction: "outbound", subject: null,
    body_html: "<p>Hallo Herr Schneider,</p><p>super, das passt perfekt! Ich schicke Ihnen gleich eine Kalendereinladung für Dienstag 10:00 Uhr.</p><p>Vorab: Das Mandat umfasst IPO-Readiness, Aufbau Finance-Team (3→8 Personen) und Investoren-Reporting. Budget liegt bei €1.800/Tag.</p><p>Freue mich auf den Austausch!</p><p>VG Niels</p>",
    status: "sent", sequence_step: null, email_opened: true, times_opened: 1, bounced: false, reply_sentiment: null,
    sent_at: "2026-02-27T15:30:00Z", thread_id: "ph-thread-c1", instantly_lead_id: "il-c01",
  },
];

function EmailFeed({ emails, entityName, emptyMessage }) {
  if (!emails || emails.length === 0) {
    return (
      <div style={{ padding:32, textAlign:"center", color:"#A0A3A9", background:"#FAFAFA", borderRadius:10, border:"1px solid #EBEBED", marginTop:16 }}>
        <div style={{ fontSize:22, marginBottom:6 }}>📨</div>
        <div style={{ fontSize:13, fontWeight:500 }}>{emptyMessage || "No outreach yet"}</div>
        <div style={{ fontSize:12, marginTop:4, color:"#A0A3A9" }}>Outreach emails will appear here once sent.</div>
      </div>
    );
  }

  const firstSubject = emails.find(e => e.subject)?.subject;
  const totalOpens = emails.reduce((sum, e) => sum + (e.times_opened || 0), 0);
  const hasBounce = emails.some(e => e.bounced);
  const replySentiment = emails.find(e => e.reply_sentiment)?.reply_sentiment;
  const maxStep = Math.max(...emails.filter(e => e.sequence_step).map(e => e.sequence_step), 0);

  return (
    <div style={{ marginTop:16 }}>
      {/* Thread header */}
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:10 }}>
        <span style={{ fontSize:14 }}>📨</span>
        <span style={{ fontSize:12, fontWeight:600, color:"#1D4ED8" }}>Email Thread with {entityName}</span>
        <span style={{ fontSize:10, color:"#A0A3A9" }}>{emails.length} messages</span>
        <span style={{ flex:1 }} />
        {replySentiment && (
          <span style={{
            padding:"2px 8px", borderRadius:4, fontSize:10, fontWeight:600,
            background: replySentiment === "interested" || replySentiment === "positive" ? "#D1FAE5" : replySentiment === "not_interested" ? "#FDECEC" : "#FEF3C7",
            color: replySentiment === "interested" || replySentiment === "positive" ? "#065F46" : replySentiment === "not_interested" ? "#C13030" : "#92400E",
          }}>{replySentiment}</span>
        )}
      </div>

      {/* Messages */}
      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
        {emails.map((msg, i) => {
          const isOutbound = msg.direction === "outbound";
          const date = msg.sent_at ? new Date(msg.sent_at) : null;
          const senderName = isOutbound
            ? (msg.sequence_step === 1 || msg.sequence_step === 2 ? "Lena" : "Niels")
            : entityName;

          return (
            <div key={msg.id || i} style={{
              maxWidth:"85%",
              alignSelf: isOutbound ? "flex-end" : "flex-start",
            }}>
              {/* Bubble */}
              <div style={{
                padding:"12px 16px",
                borderRadius: isOutbound ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
                background: isOutbound ? "#F0F4FF" : "#F7F7F8",
                border: isOutbound ? "1px solid #DBEAFE" : "1px solid #EBEBED",
              }}>
                {/* Sender + timestamp */}
                <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:6 }}>
                  <span style={{ fontSize:11, fontWeight:700, color: isOutbound ? "#1D4ED8" : "#065F46" }}>{senderName}</span>
                  {msg.sequence_step && (
                    <span style={{ padding:"1px 6px", borderRadius:3, fontSize:9, fontWeight:600, background:"#EDE9FE", color:"#6D28D9" }}>Step {msg.sequence_step}</span>
                  )}
                  <span style={{ flex:1 }} />
                  <span style={{ fontSize:10, color:"#A0A3A9" }}>
                    {date ? date.toLocaleDateString("en-GB", { day:"numeric", month:"short", hour:"2-digit", minute:"2-digit" }) : ""}
                  </span>
                </div>

                {/* Subject (first message only) */}
                {msg.subject && i === 0 && (
                  <div style={{ fontSize:12, fontWeight:700, color:"#1A1A1A", marginBottom:6 }}>{msg.subject}</div>
                )}

                {/* Body */}
                <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6 }}
                  dangerouslySetInnerHTML={{ __html: msg.body_html || msg.body || "" }}
                />
              </div>

              {/* Tracking row for outbound */}
              {isOutbound && (
                <div style={{ display:"flex", gap:8, marginTop:4, justifyContent:"flex-end", flexWrap:"wrap" }}>
                  {msg.email_opened && (
                    <span style={{ fontSize:10, color:"#065F46", fontWeight:500 }}>
                      Opened {msg.times_opened > 1 ? `${msg.times_opened}x` : ""}
                    </span>
                  )}
                  {msg.bounced && (
                    <span style={{ fontSize:10, color:"#C13030", fontWeight:600 }}>Bounced</span>
                  )}
                  {!msg.email_opened && !msg.bounced && msg.status === "sent" && (
                    <span style={{ fontSize:10, color:"#A0A3A9" }}>Delivered</span>
                  )}
                </div>
              )}

              {/* Reply sentiment for inbound */}
              {!isOutbound && msg.reply_sentiment && (
                <div style={{ display:"flex", gap:6, marginTop:4 }}>
                  <span style={{
                    fontSize:10, fontWeight:600, padding:"2px 8px", borderRadius:4,
                    background: msg.reply_sentiment === "interested" || msg.reply_sentiment === "positive" ? "#D1FAE5" : "#FEF3C7",
                    color: msg.reply_sentiment === "interested" || msg.reply_sentiment === "positive" ? "#065F46" : "#92400E",
                  }}>{msg.reply_sentiment}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Summary bar */}
      <div style={{
        display:"flex", gap:12, alignItems:"center", marginTop:12, padding:"8px 12px",
        background:"#F7F7F8", borderRadius:6, fontSize:11, color:"#6B6F76",
      }}>
        {maxStep > 0 && <span>Sequence: Step {maxStep}</span>}
        <span>Opens: {totalOpens}</span>
        <span>Bounced: {hasBounce ? "Yes" : "No"}</span>
        {replySentiment && <span>Sentiment: <strong style={{ color: replySentiment === "interested" ? "#065F46" : "#92400E" }}>{replySentiment}</strong></span>}
      </div>
    </div>
  );
}

function CompanyDetailView({ company, contacts = [], onClose, onContactsChanged, currentIndex, totalCount, onNavigate, tabLabel, role, person, companyRoles = [], onOpenRole, onOpenPerson, onOpenCompany }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [noteType, setNoteType] = useState("meeting_note");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const [showAddContact, setShowAddContact] = useState(false);
  const [newContact, setNewContact] = useState({ name: "", title: "", linkedin_url: "", email: "", phone: "" });
  const [savingContact, setSavingContact] = useState(false);
  const [outreachThreads, setOutreachThreads] = useState([]);
  const [threadContacts, setThreadContacts] = useState([]);
  const [detailTab, setDetailTab] = useState("summary");
  const [enriching, setEnriching] = useState(false);
  const [companyAgentLogs, setCompanyAgentLogs] = useState([]);
  const [roleMatches, setRoleMatches] = useState([]);
  const loadEntries = useCallback(async () => {
    if (!company) return;
    setLoading(true);
    try {
      const personId = person?.id;
      const isRealContact = personId && !personId.toString().startsWith("hm_");
      let query;

      if (person) {
        // Person view: ONLY this person's entries
        if (isRealContact) {
          query = `contact_id=eq.${personId}&order=created_at.desc&limit=200`;
        } else if (person._isHiringManager && person._roleId) {
          // Virtual HM — show role entries that mention this DM
          query = `role_id=eq.${person._roleId}&entry_type=in.(role_dm_research)&order=created_at.desc&limit=200`;
        } else {
          query = `company_id=eq.${company.id}&role_id=is.null&contact_id=is.null&order=created_at.desc&limit=200`;
        }
      } else if (role) {
        // Role view: ONLY this role's entries
        query = `role_id=eq.${role.id}&order=created_at.desc&limit=200`;
      } else {
        // Company view: ONLY company-level entries
        query = `company_id=eq.${company.id}&role_id=is.null&contact_id=is.null&order=created_at.desc&limit=200`;
      }

      const data = await supaFetch("company_dossier", query);
      const sorted = (data || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setEntries(sorted);
    } catch (e) {
      console.error("Analysis load error:", e);
    }
    setLoading(false);
  }, [company, role, person]);

  useEffect(() => { loadEntries(); }, [loadEntries]);

  const handleEnrich = async () => {
    if (enriching || !company) return;
    setEnriching(true);
    try {
      await supaPost("company_dossier", {
        company_id: company.id,
        entry_type: "agent_action",
        title: "Enrichment requested",
        content: "Manual enrichment triggered from dashboard. Agent is analyzing this company...",
        source: "dashboard",
        author: "A-Line Team",
      });
      const res = await fetch(`${SUPABASE_URL}/functions/v1/trigger-enrich`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: SUPABASE_KEY,
          Authorization: `Bearer ${SUPABASE_KEY}`,
        },
        body: JSON.stringify({ company_id: company.id }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        console.error("Enrich trigger failed:", err);
      }
      await loadEntries();
    } catch (e) {
      console.error("Enrich error:", e);
    }
    setTimeout(() => setEnriching(false), 4000);
  };

  // Load agent logs for this company
  useEffect(() => {
    if (!company) return;
    (async () => {
      try {
        const logs = await supaFetch(
          "agent_log",
          `entity_id=eq.${company.id}&entity_type=eq.company&order=created_at.desc&limit=50`
        );
        setCompanyAgentLogs(logs || []);
      } catch (e) {
        console.error("Agent log load error:", e);
      }
    })();
  }, [company]);

  // Load candidate match count for this role
  useEffect(() => {
    if (!role) { setRoleMatches([]); return; }
    (async () => {
      try {
        const matches = await supaFetch(
          "role_candidate_match",
          `role_id=eq.${role.id}&order=match_score.desc`
        );
        setRoleMatches(matches || []);
      } catch (e) { console.error("Match load error:", e); }
    })();
  }, [role]);

  // Load outreach conversation threads for this company
  useEffect(() => {
    if (!company) return;
    (async () => {
      try {
        const outreach = await supaFetch(
          "outreach",
          `company_id=eq.${company.id}&order=created_at.asc&limit=100`
        );
        if (outreach && outreach.length > 0) {
          // Group by thread_id
          const threads = {};
          for (const msg of outreach) {
            const tid = msg.thread_id || msg.id;
            if (!threads[tid]) threads[tid] = [];
            threads[tid].push(msg);
          }
          setOutreachThreads(Object.values(threads));

          // Load contact names for threads
          const contactIds = [...new Set(outreach.map(m => m.contact_id).filter(Boolean))];
          if (contactIds.length > 0) {
            const contactData = await supaFetch(
              "contact",
              `id=in.(${contactIds.join(",")})&select=id,name,title,email`
            );
            setThreadContacts(contactData || []);
          }
        } else {
          setOutreachThreads([]);
        }
      } catch (e) {
        console.error("Outreach thread load error:", e);
      }
    })();
  }, [company]);

  const handleAddNote = async () => {
    if (!noteContent.trim()) return;
    setSaving(true);
    try {
      await supaPost("company_dossier", {
        company_id: company.id,
        entry_type: noteType,
        title: noteTitle.trim() || null,
        content: noteContent.trim(),
        source: "manual",
        author: "A-Line Team",
      });
      setNoteTitle("");
      setNoteContent("");
      await loadEntries();
      setDetailTab("summary");
    } catch (e) {
      console.error("Save note error:", e);
      alert("Could not save note: " + e.message);
    }
    setSaving(false);
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      // Upload to Supabase Storage: analysis-files/{company_id}/{timestamp}_{filename}
      const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
      const storagePath = `${company.id}/${Date.now()}_${safeName}`;
      const publicUrl = await supaUploadFile("dossier-files", storagePath, file);

      // Create analysis entry for the file
      await supaPost("company_dossier", {
        company_id: company.id,
        entry_type: "file",
        title: file.name,
        content: noteContent.trim() || `File uploaded: ${file.name}`,
        source: "manual",
        source_url: publicUrl,
        file_name: file.name,
        file_size: file.size,
        file_type: file.type,
        author: "A-Line Team",
      });
      setNoteContent("");
      await loadEntries();
    } catch (err) {
      console.error("File upload error:", err);
      alert("Upload failed: " + err.message);
    }
    setUploading(false);
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAddContact = async () => {
    if (!newContact.name.trim()) return;
    setSavingContact(true);
    try {
      const nameParts = newContact.name.trim().split(/\s+/);
      const firstName = nameParts[0] || "";
      const lastName = nameParts.slice(1).join(" ") || "";
      await supaPost("contact", {
        first_name: firstName,
        last_name: lastName,
        title: newContact.title.trim() || null,
        linkedin_url: newContact.linkedin_url.trim() || null,
        email: newContact.email.trim() || null,
        phone: newContact.phone.trim() || null,
        source: "manual",
        company_id: company.id,
        is_primary: contacts.length === 0,
      });
      setNewContact({ name: "", title: "", linkedin_url: "", email: "", phone: "" });
      setShowAddContact(false);
      if (onContactsChanged) onContactsChanged();
    } catch (e) {
      console.error("Add contact error:", e);
      alert("Could not save contact: " + e.message);
    }
    setSavingContact(false);
  };

  if (!company) return null;

  const st = { lead:{bg:"#EDE9FE",color:"#6D28D9"}, prospect:{bg:"#DBEAFE",color:"#1D4ED8"}, active:{bg:"#D1FAE5",color:"#065F46"}, client:{bg:"#D1FAE5",color:"#047857"}, churned:{bg:"#FDECEC",color:"#C13030"} };
  const statusStyle = st[company.status] || { bg:"#F2F3F5", color:"#6B6F76" };
  const fitColors = { high:{bg:"#D1FAE5",color:"#065F46"}, medium:{bg:"#FFF0E1",color:"#AD5700"}, low:{bg:"#FDECEC",color:"#C13030"} };

  // Build unified timeline: merge entries + outreach threads + agent logs, sorted by date desc
  const timelineItems = [];
  entries.forEach(e => timelineItems.push({ type: "entry", data: e, date: new Date(e.created_at || 0) }));
  outreachThreads.forEach(thread => {
    const lastMsg = thread[thread.length - 1];
    timelineItems.push({ type: "outreach", data: thread, date: new Date(lastMsg?.created_at || 0) });
  });
  companyAgentLogs.forEach(log => timelineItems.push({ type: "agent_log", data: log, date: new Date(log.created_at || 0) }));
  timelineItems.sort((a, b) => b.date - a.date);

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", minWidth:0, minHeight:0, fontFamily:"'Inter',-apple-system,sans-serif" }}>

      {/* ── Top Bar ── */}
      <div style={{ padding:"10px 20px", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", gap:12 }}>
        <button onClick={onClose} style={{
          width:28, height:28, borderRadius:6, border:"1px solid #EBEBED",
          background:"#fff", cursor:"pointer", fontSize:15, color:"#6B6F76",
          display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
        }}>×</button>

        {totalCount > 1 && (
          <div style={{ display:"flex", alignItems:"center", gap:4 }}>
            <button onClick={() => onNavigate(-1)} disabled={currentIndex <= 0} style={{
              width:24, height:24, borderRadius:4, border:"1px solid #EBEBED",
              background:"#fff", cursor: currentIndex > 0 ? "pointer" : "default",
              fontSize:13, color: currentIndex > 0 ? "#1A1A1A" : "#EBEBED",
              display:"flex", alignItems:"center", justifyContent:"center",
            }}>{"\u2039"}</button>
            <span style={{ fontSize:12, color:"#A0A3A9", minWidth:90, textAlign:"center" }}>
              {currentIndex + 1} of {totalCount} in {tabLabel}
            </span>
            <button onClick={() => onNavigate(1)} disabled={currentIndex >= totalCount - 1} style={{
              width:24, height:24, borderRadius:4, border:"1px solid #EBEBED",
              background:"#fff", cursor: currentIndex < totalCount - 1 ? "pointer" : "default",
              fontSize:13, color: currentIndex < totalCount - 1 ? "#1A1A1A" : "#EBEBED",
              display:"flex", alignItems:"center", justifyContent:"center",
            }}>{"\u203A"}</button>
          </div>
        )}

        <div style={{ width:1, height:20, background:"#EBEBED" }} />
        {person ? (
          <>
            <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A" }}>{person.name}</div>
            {person.title && <span style={{ fontSize:12, color:"#A0A3A9" }}>{person.title}</span>}
            <span style={{ fontSize:12, color:"#A0A3A9" }}>at</span>
            <span onClick={() => onOpenCompany && onOpenCompany(company)} style={{ fontSize:13, fontWeight:600, color:"#5B5FC7", cursor:"pointer" }}>{company.name} ↗</span>
          </>
        ) : role ? (
          <>
            <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A" }}>{cleanTitle(role.title)}</div>
            <span style={{ fontSize:12, color:"#A0A3A9" }}>at</span>
            <span onClick={() => onOpenCompany && onOpenCompany(company)} style={{ fontSize:13, fontWeight:600, color:"#5B5FC7", cursor:"pointer" }}>{company.name} ↗</span>
            <TierPill tier={role.tier} />
          </>
        ) : (
          <>
            <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A" }}>{company.name}</div>
            {company.domain && (
              <a href={`https://${company.domain}`} target="_blank" rel="noopener" style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{company.domain} ↗</a>
            )}
          </>
        )}
      </div>

      {/* ── Two-Column Body ── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* LEFT — Tabbed Content */}
        <div style={{ flex:3, display:"flex", flexDirection:"column", borderRight:"1px solid #EBEBED", minHeight:0 }}>

          {/* Sub-nav tabs */}
          <div style={{ display:"flex", gap:0, borderBottom:"1px solid #EBEBED", padding:"0 24px", flexShrink:0 }}>
            {(person ? [
              { key:"summary", label:"Summary" },
              { key:"activity", label:"Analysis", count:timelineItems.length },
              { key:"company", label:"Company", count:null },
              { key:"roles", label:"Roles", count:companyRoles.length },
            ] : role ? [
              { key:"summary", label:"Summary" },
              { key:"activity", label:"Analysis", count:timelineItems.length },
              { key:"contacts", label:"Hiring Manager", count: role.hiring_manager_name ? 1 : 0 },
              { key:"candidates", label:"Candidates", count:roleMatches.length },
              { key:"company", label:"Company", count:null },
            ] : [
              { key:"summary", label:"Summary" },
              { key:"activity", label:"Analysis", count:timelineItems.length },
              { key:"contacts", label:"Contacts", count:contacts.length },
              { key:"candidates", label:"Candidates", count:0 },
            ]).map(t => {
              const active = detailTab === t.key;
              return (
                <button key={t.key} onClick={() => setDetailTab(t.key)} style={{
                  padding:"10px 16px", fontSize:12, fontWeight:active ? 600 : 400, cursor:"pointer",
                  border:"none", borderBottom: active ? "2px solid #1A1A1A" : "2px solid transparent",
                  background:"transparent", color: active ? "#1A1A1A" : "#A0A3A9",
                  fontFamily:"inherit", marginBottom:-1,
                }}>{t.label}{t.count != null ? ` (${t.count})` : ""}</button>
              );
            })}
          </div>

          {/* Tab content */}
          <div style={{ flex:1, overflow:"auto", padding:"20px 24px" }}>

            {/* ── Summary Tab ── */}
            {detailTab === "summary" && (
              person ? (
                /* Person Summary */
                <div>
                  {/* Person header card */}
                  <div style={{ background:"#F7F7F8", borderRadius:10, padding:"16px 18px", marginBottom:20 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:12 }}>
                      <div style={{ width:48, height:48, borderRadius:10, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontWeight:800, fontSize:18, flexShrink:0 }}>
                        {person.name?.charAt(0) || "?"}
                      </div>
                      <div style={{ flex:1 }}>
                        <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A" }}>{person.name}</div>
                        <div style={{ fontSize:12, color:"#6B6F76", marginTop:2 }}>
                          {[person.role_at_company || person.title, person.company_name || company?.name].filter(Boolean).join(" at ")}
                        </div>
                        {person.linkedin_url && (
                          <a href={person.linkedin_url} target="_blank" rel="noopener" style={{ fontSize:11, color:"#0A66C2", textDecoration:"none", fontWeight:600, marginTop:4, display:"inline-block" }}>LinkedIn Profile ↗</a>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Decision Maker assessment */}
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Decision Maker Assessment</div>
                    <div style={{ display:"flex", alignItems:"center", gap:10, padding:"12px 16px", background:"#F7F7F8", borderRadius:8 }}>
                      <div style={{
                        width:40, height:40, borderRadius:8, display:"flex", alignItems:"center", justifyContent:"center",
                        fontSize:16, fontWeight:800,
                        background: person.is_decision_maker ? "#FDECEC" : "#F2F3F5",
                        color: person.is_decision_maker ? "#C13030" : "#A0A3A9",
                      }}>
                        {person.decision_maker_score != null ? person.decision_maker_score : (person.is_decision_maker ? "DM" : "—")}
                      </div>
                      <div>
                        <div style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>
                          {person.is_decision_maker ? "Decision Maker" : "Not flagged as DM"}
                        </div>
                        {person.seniority && (
                          <div style={{ fontSize:11, color:"#6B6F76", marginTop:2 }}>Seniority: {person.seniority}</div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Personal Hooks */}
                  {person.personal_hooks && (
                    <div style={{ marginBottom:20 }}>
                      <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Personal Hooks</div>
                      <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                        {(Array.isArray(person.personal_hooks) ? person.personal_hooks : [person.personal_hooks]).map((hook, i) => (
                          <div key={i} style={{ fontSize:12, color:"#1A1A1A", padding:"8px 12px", background:"#EDE9FE", borderRadius:6, lineHeight:1.5 }}>
                            {hook}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Contact details compact grid */}
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Contact Details</div>
                    <div style={{ display:"grid", gridTemplateColumns:"80px 1fr", gap:"6px 12px", fontSize:12, background:"#F7F7F8", padding:"12px 16px", borderRadius:8 }}>
                      {person.email && <>
                        <div style={{ color:"#A0A3A9" }}>Email</div>
                        <div><a href={`mailto:${person.email}`} style={{ color:"#5B5FC7", textDecoration:"none" }}>{person.email}</a></div>
                      </>}
                      {person.phone && <>
                        <div style={{ color:"#A0A3A9" }}>Phone</div>
                        <div style={{ color:"#1A1A1A" }}>{person.phone}</div>
                      </>}
                      {person.seniority && <>
                        <div style={{ color:"#A0A3A9" }}>Seniority</div>
                        <div style={{ color:"#1A1A1A" }}>{person.seniority}</div>
                      </>}
                      {person.source && <>
                        <div style={{ color:"#A0A3A9" }}>Source</div>
                        <div><SourcePill source={person.source} /></div>
                      </>}
                    </div>
                  </div>
                </div>
              ) : role ? (
                /* Role Summary */
                <div>
                  {/* Role header card */}
                  <div style={{ background:"#F7F7F8", borderRadius:10, padding:"16px 18px", marginBottom:20 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:8 }}>
                      <TierPill tier={role.tier} />
                      <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A", flex:1 }}>{cleanTitle(role.title)}</div>
                      <Score v={role.final_score ?? role.qualification_score ?? role.rule_score} />
                    </div>
                    <div style={{ fontSize:12, color:"#6B6F76", display:"flex", gap:12, alignItems:"center", flexWrap:"wrap" }}>
                      <span>{company?.name}</span>
                      {role.location && <span>{cleanLocation(role.location)}</span>}
                      <EngPill type={role.engagement_type} />
                    </div>
                  </div>

                  {/* Sourcing Brief */}
                  {(() => {
                    const brief = typeof role.sourcing_brief === "string" ? (() => { try { return JSON.parse(role.sourcing_brief); } catch { return null; } })() : role.sourcing_brief;
                    if (!brief) return null;
                    return (
                      <div style={{ marginBottom:20 }}>
                        <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:10 }}>Sourcing Brief</div>

                        {brief.must_have && brief.must_have.length > 0 && (
                          <div style={{ marginBottom:12 }}>
                            <div style={{ fontSize:11, fontWeight:600, color:"#065F46", marginBottom:4 }}>Must-Have</div>
                            <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                              {brief.must_have.map((item, i) => (
                                <span key={i} style={{ padding:"4px 10px", borderRadius:4, fontSize:11, background:"#D1FAE5", color:"#065F46" }}>{item}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {brief.nice_to_have && brief.nice_to_have.length > 0 && (
                          <div style={{ marginBottom:12 }}>
                            <div style={{ fontSize:11, fontWeight:600, color:"#AD5700", marginBottom:4 }}>Nice-to-Have</div>
                            <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                              {brief.nice_to_have.map((item, i) => (
                                <span key={i} style={{ padding:"4px 10px", borderRadius:4, fontSize:11, background:"#FFF0E1", color:"#AD5700" }}>{item}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {brief.ideal_candidate_profile && (
                          <div style={{ marginBottom:12 }}>
                            <div style={{ fontSize:11, fontWeight:600, color:"#6D28D9", marginBottom:4 }}>Ideal Profile</div>
                            <div style={{ fontSize:11, color:"#6B6F76", background:"#F7F7F8", padding:"8px 10px", borderRadius:6, lineHeight:1.5 }}>
                              {brief.ideal_candidate_profile.background && <div><strong>Background:</strong> {brief.ideal_candidate_profile.background}</div>}
                              {brief.ideal_candidate_profile.years_experience && <div><strong>Experience:</strong> {brief.ideal_candidate_profile.years_experience}</div>}
                              {brief.ideal_candidate_profile.titles_to_search && <div><strong>Target titles:</strong> {brief.ideal_candidate_profile.titles_to_search.join(", ")}</div>}
                            </div>
                          </div>
                        )}

                        {brief.red_flags && brief.red_flags.length > 0 && (
                          <div style={{ marginBottom:12 }}>
                            <div style={{ fontSize:11, fontWeight:600, color:"#C13030", marginBottom:4 }}>Red Flags</div>
                            <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                              {brief.red_flags.map((item, i) => (
                                <span key={i} style={{ padding:"4px 10px", borderRadius:4, fontSize:11, background:"#FDECEC", color:"#C13030" }}>{item}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {(brief.urgency || brief.compensation_signal) && (
                          <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
                            {brief.urgency && <span style={{ padding:"4px 10px", borderRadius:4, fontSize:11, fontWeight:600, background:"#FFF0E1", color:"#AD5700" }}>Urgency: {brief.urgency}</span>}
                            {brief.compensation_signal && <span style={{ padding:"4px 10px", borderRadius:4, fontSize:11, fontWeight:600, background:"#F2F3F5", color:"#6B6F76" }}>{brief.compensation_signal}</span>}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Engagement Reasoning */}
                  {role.engagement_reasoning && (
                    <div style={{ marginBottom:20 }}>
                      <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:6 }}>Engagement Reasoning</div>
                      <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.7, background:"#F7F7F8", padding:"12px 16px", borderRadius:8, whiteSpace:"pre-wrap" }}>{role.engagement_reasoning}</div>
                    </div>
                  )}

                  {/* Outreach Angle */}
                  {role.outreach_angle && (
                    <div style={{ marginBottom:20 }}>
                      <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:6 }}>Outreach Angle</div>
                      <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.7, background:"#EDE9FE", padding:"12px 16px", borderRadius:8, whiteSpace:"pre-wrap" }}>{role.outreach_angle}</div>
                    </div>
                  )}

                  {/* Requirements Summary */}
                  {role.requirements_summary && (
                    <div style={{ marginBottom:20 }}>
                      <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:6 }}>Requirements</div>
                      <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.7, background:"#F7F7F8", padding:"12px 16px", borderRadius:8, whiteSpace:"pre-wrap" }}>{role.requirements_summary}</div>
                    </div>
                  )}
                </div>
              ) : (
                /* Company Summary */
                <div>
                  {/* Summary text highlighted card */}
                  {company.summary && (
                    <div style={{ background:"#EDE9FE", borderRadius:10, padding:"16px 18px", marginBottom:20, border:"1px solid #DDD6FE" }}>
                      <div style={{ fontSize:13, color:"#1A1A1A", lineHeight:1.7, fontWeight:500 }}>{company.summary}</div>
                    </div>
                  )}

                  {/* Key metrics row */}
                  <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:20 }}>
                    {company.composite_score != null && (
                      <span style={{ padding:"4px 12px", borderRadius:6, fontSize:12, fontWeight:700, background:"#F2F3F5", color:"#1A1A1A" }}>Score: {company.composite_score}</span>
                    )}
                    {company.arteq_fit && fitColors[company.arteq_fit] && (
                      <span style={{ padding:"4px 12px", borderRadius:6, fontSize:12, fontWeight:600, background:fitColors[company.arteq_fit].bg, color:fitColors[company.arteq_fit].color }}>{company.arteq_fit} fit</span>
                    )}
                    {company.revenue_estimate && (
                      <span style={{ padding:"4px 12px", borderRadius:6, fontSize:12, fontWeight:500, background:"#D1FAE5", color:"#065F46" }}>{company.revenue_estimate}</span>
                    )}
                  </div>

                  {/* Description */}
                  {company.description && (
                    <div style={{ marginBottom:20 }}>
                      <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:6 }}>Description</div>
                      <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.7 }}>{company.description}</div>
                    </div>
                  )}

                  {/* Business context */}
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Business Context</div>
                    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8 }}>
                      {company.funding_stage && company.funding_stage !== "unknown" && (
                        <div style={{ background:"#F7F7F8", borderRadius:6, padding:"10px 12px" }}>
                          <div style={{ fontSize:10, color:"#A0A3A9", marginBottom:2 }}>Funding</div>
                          <div style={{ fontSize:12, fontWeight:600, color:"#1A1A1A" }}>{company.funding_stage}</div>
                        </div>
                      )}
                      {company.headcount && (
                        <div style={{ background:"#F7F7F8", borderRadius:6, padding:"10px 12px" }}>
                          <div style={{ fontSize:10, color:"#A0A3A9", marginBottom:2 }}>Headcount</div>
                          <div style={{ fontSize:12, fontWeight:600, color:"#1A1A1A" }}>~{company.headcount}</div>
                        </div>
                      )}
                      {company.industry && (
                        <div style={{ background:"#F7F7F8", borderRadius:6, padding:"10px 12px" }}>
                          <div style={{ fontSize:10, color:"#A0A3A9", marginBottom:2 }}>Industry</div>
                          <div style={{ fontSize:12, fontWeight:600, color:"#1A1A1A" }}>{company.industry}</div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Analysis HTML - company_analysis entry */}
                  {entries.filter(e => e.entry_type === "company_analysis").map(e => (
                    <div key={e.id} style={{ marginBottom:20 }}>
                      <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:6 }}>AI Analysis</div>
                      <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.8, background:"#F7F7F8", padding:"14px 16px", borderRadius:8 }}
                        dangerouslySetInnerHTML={{ __html: e.content }}
                      />
                    </div>
                  ))}
                </div>
              )
            )}

            {/* ── Activity Tab ── */}
            {detailTab === "activity" && (
              <>
                {loading ? (
                  <div style={{ padding:40, textAlign:"center", color:"#A0A3A9", fontSize:13 }}>Loading…</div>
                ) : timelineItems.length === 0 ? (
                  <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
                    <div style={{ fontSize:22, marginBottom:6 }}>📋</div>
                    <div style={{ fontSize:13, fontWeight:500 }}>No activity yet</div>
                    <div style={{ fontSize:12, marginTop:4 }}>Signals and outreach will appear here.</div>
                  </div>
                ) : (
                  <div style={{ position:"relative" }}>
                    {/* Timeline line */}
                    <div style={{ position:"absolute", left:11, top:8, bottom:8, width:2, background:"#EBEBED" }} />

                    {timelineItems.map((item, idx) => {
                      if (item.type === "agent_log") {
                        const log = item.data;
                        const ACTION_STYLE = {
                          promote_company:   { icon:"⬆", bg:"#D1FAE5", color:"#065F46", label:"Promoted" },
                          downgrade_company: { icon:"⬇", bg:"#FDECEC", color:"#C13030", label:"Downgraded" },
                          expire_role:       { icon:"⏰", bg:"#FFF0E1", color:"#AD5700", label:"Expired" },
                          enrich_single:     { icon:"✨", bg:"#EDE9FE", color:"#6D28D9", label:"Enriched" },
                          enrich_contact:    { icon:"✉", bg:"#EDE9FE", color:"#6D28D9", label:"Enriched" },
                          outreach_draft:    { icon:"📝", bg:"#DBEAFE", color:"#1D4ED8", label:"Draft" },
                          outreach_sent:     { icon:"📨", bg:"#D1FAE5", color:"#065F46", label:"Sent" },
                          sdr_handoff_ae:    { icon:"🤝", bg:"#EDE9FE", color:"#6D28D9", label:"Handoff" },
                        };
                        const ast = ACTION_STYLE[log.action] || { icon:"🤖", bg:"#F2F3F5", color:"#6B6F76", label:log.action };
                        const logDate = log.created_at ? new Date(log.created_at) : null;
                        return (
                          <div key={`log-${log.id || idx}`} style={{ position:"relative", paddingLeft:32, paddingBottom:16 }}>
                            <div style={{
                              position:"absolute", left:4, top:4,
                              width:16, height:16, borderRadius:"50%",
                              background:ast.bg, border:`2px solid ${ast.color}`,
                              display:"flex", alignItems:"center", justifyContent:"center",
                              fontSize:8,
                            }}>{ast.icon}</div>
                            <div style={{ background:"#F7F7F8", borderRadius:8, padding:"12px 14px" }}>
                              <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:6 }}>
                                <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:600, background:ast.bg, color:ast.color }}>{ast.label}</span>
                                <span style={{ fontSize:10, color:"#A0A3A9" }}>Agent</span>
                                <span style={{ flex:1 }} />
                                <span style={{ fontSize:10, color:"#A0A3A9", whiteSpace:"nowrap" }}>
                                  {logDate ? logDate.toLocaleDateString("en-GB", { day:"numeric", month:"short", year:"numeric" }) : "—"}
                                </span>
                              </div>
                              <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, whiteSpace:"pre-wrap" }}>
                                {log.reason || "—"}
                              </div>
                            </div>
                          </div>
                        );
                      }
                      if (item.type === "outreach") {
                        const thread = item.data;
                        const firstMsg = thread[0];
                        return (
                          <div key={`outreach-${firstMsg?.thread_id || idx}`} style={{ position:"relative", paddingLeft:32, paddingBottom:16 }}>
                            <div style={{
                              position:"absolute", left:4, top:4,
                              width:16, height:16, borderRadius:"50%",
                              background:"#DBEAFE", border:"2px solid #1D4ED8",
                              display:"flex", alignItems:"center", justifyContent:"center",
                              fontSize:8,
                            }}>📨</div>
                            <OutreachThread thread={thread} contacts={threadContacts} />
                          </div>
                        );
                      }

                      // Analysis entry
                      const entry = item.data;
                      const et = ENTRY_TYPE[entry.entry_type] || ENTRY_TYPE.note;
                      const date = entry.created_at ? new Date(entry.created_at) : null;
                      return (
                        <div key={entry.id || `entry-${idx}`} style={{ position:"relative", paddingLeft:32, paddingBottom:16 }}>
                          {/* Timeline dot */}
                          <div style={{
                            position:"absolute", left:4, top:4,
                            width:16, height:16, borderRadius:"50%",
                            background:et.bg, border:`2px solid ${et.color}`,
                            display:"flex", alignItems:"center", justifyContent:"center",
                            fontSize:8,
                          }}>{et.icon}</div>

                          <div style={{ background:"#F7F7F8", borderRadius:8, padding:"12px 14px" }}>
                            {/* Meta row */}
                            <div style={{ display:"flex", alignItems:"center", gap:6, marginBottom:6 }}>
                              <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:600, background:et.bg, color:et.color }}>{et.label}</span>
                              {entry.source && entry.source !== "manual" && (
                                <span style={{ fontSize:10, color:"#A0A3A9" }}>{entry.source}</span>
                              )}
                              {entry.author && (
                                <span style={{ fontSize:10, color:"#6B6F76", fontWeight:500 }}>{entry.author}</span>
                              )}
                              <span style={{ flex:1 }} />
                              <span style={{ fontSize:10, color:"#A0A3A9", whiteSpace:"nowrap" }}>
                                {date ? date.toLocaleDateString("en-GB", { day:"numeric", month:"short", year:"numeric" }) : "—"}
                              </span>
                            </div>

                            {/* Title */}
                            {entry.title && (
                              <div style={{ fontSize:13, fontWeight:600, color:"#1A1A1A", lineHeight:1.4, marginBottom:4 }}>
                                {entry.source_url ? (
                                  <a href={entry.source_url} target="_blank" rel="noopener" style={{ color:"#1A1A1A", textDecoration:"none" }}
                                    onMouseEnter={e => e.target.style.color="#5B5FC7"}
                                    onMouseLeave={e => e.target.style.color="#1A1A1A"}
                                  >{entry.title}</a>
                                ) : entry.title}
                              </div>
                            )}

                            {/* File attachment card */}
                            {entry.entry_type === "file" && entry.source_url && (
                              <a href={entry.source_url} target="_blank" rel="noopener" style={{
                                display:"flex", alignItems:"center", gap:10,
                                padding:"8px 12px", borderRadius:6,
                                background:"#fff", border:"1px solid #EBEBED",
                                textDecoration:"none", color:"#1A1A1A",
                                marginBottom: entry.content && !entry.content.startsWith("File uploaded:") ? 6 : 0,
                              }}>
                                <span style={{ fontSize:20 }}>{fileIcon(entry.file_type)}</span>
                                <div style={{ flex:1, minWidth:0 }}>
                                  <div style={{ fontSize:12, fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                                    {entry.file_name || entry.title || "Download"}
                                  </div>
                                  {entry.file_size && (
                                    <div style={{ fontSize:10, color:"#A0A3A9", marginTop:1 }}>{formatFileSize(entry.file_size)}</div>
                                  )}
                                </div>
                                <span style={{ fontSize:11, color:"#5B5FC7", fontWeight:600, whiteSpace:"nowrap" }}>Open ↗</span>
                              </a>
                            )}

                            {/* Content */}
                            {entry.content && !(entry.entry_type === "file" && entry.content.startsWith("File uploaded:")) && (
                              <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.8 }}
                                dangerouslySetInnerHTML={{ __html: entry.content }}
                              />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}

            {/* ── Contacts / Hiring Manager Tab ── */}
            {detailTab === "contacts" && (
              role ? (
                /* Hiring Manager view for roles */
                <div>
                  {role.hiring_manager_name ? (
                    <>
                      <div style={{ border:"1px solid #EBEBED", borderRadius:10, padding:"20px 22px", background:"#FAFAFA" }}>
                        <div style={{ display:"flex", alignItems:"center", gap:14, marginBottom:16 }}>
                          <div style={{ width:48, height:48, borderRadius:10, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", fontSize:18, fontWeight:700, color:"#fff", flexShrink:0 }}>
                            {role.hiring_manager_name.charAt(0)}
                          </div>
                          <div>
                            <div style={{ fontSize:16, fontWeight:700, color:"#1A1A1A" }}>{role.hiring_manager_name}</div>
                            {role.hiring_manager_title && <div style={{ fontSize:12, color:"#6B6F76", marginTop:2 }}>{role.hiring_manager_title}</div>}
                          </div>
                          {role.hiring_manager_confidence && (
                            <span style={{
                              marginLeft:"auto", padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:600,
                              background: role.hiring_manager_confidence === "high" ? "#D1FAE5" : role.hiring_manager_confidence === "medium" ? "#FEF3C7" : "#F2F3F5",
                              color: role.hiring_manager_confidence === "high" ? "#065F46" : role.hiring_manager_confidence === "medium" ? "#92400E" : "#6B6F76",
                            }}>{role.hiring_manager_confidence} confidence</span>
                          )}
                        </div>
                        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
                          {role.hiring_manager_linkedin && (
                            <a href={role.hiring_manager_linkedin} target="_blank" rel="noopener" onClick={e => e.stopPropagation()} style={{
                              padding:"6px 14px", borderRadius:6, background:"#0A66C2", color:"#fff",
                              fontSize:12, fontWeight:600, textDecoration:"none", display:"inline-flex", alignItems:"center", gap:4,
                            }}>LinkedIn Profile</a>
                          )}
                        </div>
                      </div>

                      {/* Email Feed for Hiring Manager */}
                      <EmailFeed emails={PLACEHOLDER_EMAILS_HM} entityName={role.hiring_manager_name} />
                    </>
                  ) : (
                    <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
                      <div style={{ fontSize:22, marginBottom:6 }}>🎯</div>
                      <div style={{ fontSize:13, fontWeight:500 }}>Pending enrichment</div>
                      <div style={{ fontSize:12, marginTop:4 }}>Hiring manager will be identified during role enrichment.</div>
                    </div>
                  )}
                </div>
              ) : (
                /* Contacts view for companies */
                <div>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
                    <div style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>
                      {contacts.length} {contacts.length === 1 ? "contact" : "contacts"}
                    </div>
                    <button onClick={() => setShowAddContact(!showAddContact)} style={{
                      padding:"5px 14px", borderRadius:6, fontSize:12, fontWeight:600, cursor:"pointer",
                      border:"1px solid #EBEBED", background: showAddContact ? "#1A1A1A" : "#fff",
                      color: showAddContact ? "#fff" : "#6B6F76", fontFamily:"inherit",
                    }}>{showAddContact ? "Cancel" : "+ Add Contact"}</button>
                  </div>

                  {showAddContact && (
                    <div style={{ background:"#FAFAFA", borderRadius:8, padding:16, marginBottom:16, border:"1px solid #EBEBED" }}>
                      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                        <input value={newContact.name} onChange={e => setNewContact(p => ({...p, name: e.target.value}))} placeholder="Name *" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none", gridColumn: "1 / -1" }} />
                        <input value={newContact.title} onChange={e => setNewContact(p => ({...p, title: e.target.value}))} placeholder="Title (e.g. CEO)" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                        <input value={newContact.linkedin_url} onChange={e => setNewContact(p => ({...p, linkedin_url: e.target.value}))} placeholder="LinkedIn URL" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                        <input value={newContact.email} onChange={e => setNewContact(p => ({...p, email: e.target.value}))} placeholder="Email" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                        <input value={newContact.phone} onChange={e => setNewContact(p => ({...p, phone: e.target.value}))} placeholder="Phone" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                      </div>
                      <button onClick={handleAddContact} disabled={savingContact || !newContact.name.trim()} style={{
                        marginTop:10, padding:"7px 18px", borderRadius:6, border:"none", fontSize:12, fontWeight:600, cursor: newContact.name.trim() ? "pointer" : "default", fontFamily:"inherit",
                        background: newContact.name.trim() ? "#1A1A1A" : "#EBEBED", color: newContact.name.trim() ? "#fff" : "#A0A3A9",
                      }}>{savingContact ? "Saving..." : "Save Contact"}</button>
                    </div>
                  )}

                  {contacts.length === 0 && !showAddContact ? (
                    <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
                      <div style={{ fontSize:22, marginBottom:6 }}>👤</div>
                      <div style={{ fontSize:13, fontWeight:500 }}>No contacts yet</div>
                      <div style={{ fontSize:12, marginTop:4 }}>Click "+ Add Contact" to add one.</div>
                    </div>
                  ) : (
                    <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                      {contacts.map((c, i) => (
                        <div key={c.id || i} onClick={() => onOpenPerson && onOpenPerson(c)} style={{ display:"flex", alignItems:"center", gap:12, padding:"12px 14px", background:"#F7F7F8", borderRadius:10, cursor:"pointer" }}
                          onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                          onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                          <div style={{ width:36, height:36, borderRadius:8, background: c.is_decision_maker ? "#1A1A1A" : "#EBEBED", display:"flex", alignItems:"center", justifyContent:"center", fontSize:14, fontWeight:700, color: c.is_decision_maker ? "#fff" : "#6B6F76", flexShrink:0 }}>
                            {c.name?.charAt(0) || "?"}
                          </div>
                          <div style={{ flex:1, minWidth:0 }}>
                            <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                              <span style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>{c.name}</span>
                              {c.is_decision_maker && <span style={{ fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3, background:"#FDECEC", color:"#C13030" }}>DM</span>}
                            </div>
                            <div style={{ fontSize:11, color:"#6B6F76", marginTop:1 }}>{c.role_at_company || c.title || ""}</div>
                            <div style={{ display:"flex", gap:8, marginTop:4, flexWrap:"wrap" }}>
                              {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{ fontSize:11, color:"#0A66C2", textDecoration:"none", fontWeight:600 }}>LinkedIn</a>}
                              {c.email && <a href={`mailto:${c.email}`} onClick={e=>e.stopPropagation()} style={{ fontSize:11, color:"#5B5FC7", textDecoration:"none" }}>{c.email}</a>}
                              {c.phone && <span style={{ fontSize:11, color:"#6B6F76" }}>{c.phone}</span>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            )}

            {/* ── Candidates Tab ── */}
            {detailTab === "candidates" && (
              <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
                <div style={{ fontSize:22, marginBottom:6 }}>⊙</div>
                <div style={{ fontSize:13, fontWeight:500 }}>Candidate matching coming soon</div>
              </div>
            )}

            {/* ── Company Tab (role + person view) ── */}
            {detailTab === "company" && company && (
              <div>
                <div style={{ background:"#F7F7F8", borderRadius:10, padding:"16px 18px", marginBottom:20, cursor:"pointer" }}
                  onClick={() => onOpenCompany && onOpenCompany(company)}
                  onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                  onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                  <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                    <div style={{ width:36, height:36, borderRadius:8, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontWeight:800, fontSize:15, flexShrink:0 }}>
                      {company.name?.charAt(0) || "?"}
                    </div>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:14, fontWeight:700, color:"#5B5FC7" }}>{company.name} ↗</div>
                      <div style={{ fontSize:11, color:"#6B6F76" }}>
                        {[company.industry, company.hq_city, company.headcount ? `~${company.headcount} employees` : null].filter(Boolean).join(" · ") || "—"}
                      </div>
                    </div>
                  </div>
                </div>

                <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"8px 12px", fontSize:12, marginBottom:20 }}>
                  {[
                    ["Domain", company.domain],
                    ["Industry", company.industry || "—"],
                    ["HQ", company.hq_city || "—"],
                    ["Founded", company.founded_year || "—"],
                    ["Headcount", company.headcount || "—"],
                    ["Funding", [company.funding_stage, company.funding_amount].filter(x => x && x !== "unknown").join(" — ") || "—"],
                    ["Status", company.status || "—"],
                    ["Fit", company.arteq_fit],
                    ["Pipeline", company.pipeline_stage],
                  ].map(([label, value]) => {
                    let rendered = value || "—";
                    if (label === "Domain" && value) rendered = <a href={`https://${value}`} target="_blank" rel="noopener" style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{value} ↗</a>;
                    else if (label === "Fit" && value && fitColors[value]) rendered = <span style={{ padding:"2px 6px", borderRadius:3, fontSize:11, fontWeight:500, background:fitColors[value].bg, color:fitColors[value].color }}>{value}</span>;
                    else if (label === "Pipeline" && value) rendered = <span style={{ padding:"2px 6px", borderRadius:3, fontSize:11, fontWeight:600, background:"#F2F3F5", color:"#6B6F76" }}>{value.replace(/_/g," ")}</span>;
                    return (
                      <div key={label} style={{ display:"contents" }}>
                        <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                        <div style={{ color:"#1A1A1A" }}>{rendered}</div>
                      </div>
                    );
                  })}
                </div>

                {company.description && (
                  <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, marginBottom:20, padding:"12px 16px", background:"#F7F7F8", borderRadius:8 }}>
                    {company.description}
                  </div>
                )}

                {/* Other contacts at this company */}
                {contacts.length > 0 && (
                  <div style={{ marginTop:8, paddingTop:16, borderTop:"1px solid #EBEBED" }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:10 }}>Contacts ({contacts.length})</div>
                    <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                      {contacts.filter(c => c.id !== person?.id && c.name !== person?.name).map((c, i) => (
                        <div key={c.id || i} onClick={() => onOpenPerson && onOpenPerson(c)} style={{ display:"flex", alignItems:"center", gap:10, padding:"10px 12px", background:"#F7F7F8", borderRadius:8, cursor:"pointer" }}
                          onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                          onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                          <div style={{ width:28, height:28, borderRadius:6, background: c.is_decision_maker ? "#1A1A1A" : "#EBEBED", display:"flex", alignItems:"center", justifyContent:"center", fontSize:11, fontWeight:700, color: c.is_decision_maker ? "#fff" : "#6B6F76", flexShrink:0 }}>
                            {c.name?.charAt(0) || "?"}
                          </div>
                          <div>
                            <div style={{ fontSize:12, fontWeight:600, color:"#1A1A1A" }}>{c.name}</div>
                            <div style={{ fontSize:11, color:"#6B6F76" }}>{c.role_at_company || c.title || ""}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── Roles Tab (person view) ── */}
            {detailTab === "roles" && (
              <div>
                {companyRoles.length === 0 ? (
                  <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
                    <div style={{ fontSize:22, marginBottom:6 }}>⊙</div>
                    <div style={{ fontSize:13, fontWeight:500 }}>No open roles at {company?.name}</div>
                  </div>
                ) : (
                  <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                    {companyRoles.map(r => {
                      const isHMForRole = person?._isHiringManager && person?._roleId === r.id;
                      return (
                        <div key={r.id} onClick={() => onOpenRole && onOpenRole(r)} style={{
                          border: isHMForRole ? "2px solid #5B5FC7" : "1px solid #EBEBED",
                          borderRadius:10, padding:"14px 16px", cursor:"pointer",
                          background: isHMForRole ? "#F5F3FF" : "#FAFAFA",
                        }}
                          onMouseEnter={e => { if (!isHMForRole) e.currentTarget.style.background="#F0F0F2"; }}
                          onMouseLeave={e => { e.currentTarget.style.background = isHMForRole ? "#F5F3FF" : "#FAFAFA"; }}>
                          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
                            <TierPill tier={r.tier} />
                            <span style={{ fontWeight:600, fontSize:13, color:"#1A1A1A", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{cleanTitle(r.title)}</span>
                            <Score v={r.final_score ?? r.rule_score} />
                          </div>
                          {isHMForRole && (
                            <div style={{ marginBottom:6 }}>
                              <span style={{ fontSize:10, fontWeight:600, padding:"2px 6px", borderRadius:3, background:"#EDE9FE", color:"#6D28D9" }}>Hiring Manager</span>
                            </div>
                          )}
                          <div style={{ fontSize:11, color:"#6B6F76", display:"flex", gap:12, alignItems:"center" }}>
                            {r.location && <span>{cleanLocation(r.location)}</span>}
                            <EngPill type={r.engagement_type} />
                            {r.posted_at && <span style={{ fontSize:10, color:"#A0A3A9" }}>{new Date(r.posted_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"})}</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

          </div>
        </div>

        {/* RIGHT — Details */}
        <div style={{ flex:2, overflow:"auto", padding:"20px 24px" }}>
          {person ? (
            <>
              {/* Person Details */}
              <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12 }}>Person Details</div>
              <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"8px 12px", fontSize:12 }}>
                {[
                  ["Name", person.name || "—"],
                  ["Title", person.role_at_company || person.title || "—"],
                  ["Email", person.email],
                  ["Phone", person.phone || "—"],
                  ["LinkedIn", person.linkedin_url],
                  ["Source", null],
                  ["Seniority", person.seniority || "—"],
                  ["DM", person.is_decision_maker ? "Yes" : "No"],
                  ["Added", person.created_at ? new Date(person.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : "—"],
                ].map(([label, value]) => {
                  let rendered = value || "—";
                  if (label === "Email" && value) rendered = <a href={`mailto:${value}`} style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{value}</a>;
                  else if (label === "LinkedIn" && value) rendered = <a href={value} target="_blank" rel="noopener" style={{ fontSize:12, color:"#0A66C2", textDecoration:"none", fontWeight:600 }}>Profile ↗</a>;
                  else if (label === "Source") rendered = <SourcePill source={person.source} />;
                  else if (label === "DM" && person.is_decision_maker) rendered = <span style={{ fontSize:11, fontWeight:700, padding:"2px 6px", borderRadius:3, background:"#FDECEC", color:"#C13030" }}>Decision Maker</span>;
                  return (
                    <div key={label} style={{ display:"contents" }}>
                      <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                      <div style={{ color:"#1A1A1A" }}>{rendered}</div>
                    </div>
                  );
                })}
              </div>

              {/* Company section below person */}
              <div style={{ marginTop:28, paddingTop:20, borderTop:"1px solid #EBEBED" }}>
                <div onClick={() => onOpenCompany && onOpenCompany(company)} style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12, cursor:"pointer", display:"inline-flex", alignItems:"center", gap:4 }}>Company <span style={{ fontSize:9, color:"#5B5FC7" }}>↗</span></div>
                <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"8px 12px", fontSize:12 }}>
                  {[
                    ["Name", company.name],
                    ["Domain", company.domain || "—"],
                    ["Industry", company.industry || "—"],
                    ["Fit", company.arteq_fit],
                    ["Funding", company.funding_stage && company.funding_stage !== "unknown" ? company.funding_stage : "—"],
                    ["Headcount", company.headcount || "—"],
                    ["HQ", company.hq_city || "—"],
                  ].map(([label, value]) => {
                    let rendered = value || "—";
                    if (label === "Fit" && value && fitColors[value]) {
                      rendered = <span style={{ padding:"2px 6px", borderRadius:3, fontSize:11, fontWeight:500, background:fitColors[value].bg, color:fitColors[value].color }}>{value}</span>;
                    }
                    return (
                      <div key={label} style={{ display:"contents" }}>
                        <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                        <div style={{ color:"#1A1A1A" }}>{rendered}</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Roles at this company (from person view) */}
              {companyRoles.length > 0 && (
                <div style={{ marginTop:20, paddingTop:16, borderTop:"1px solid #EBEBED" }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:10 }}>Open Roles ({companyRoles.length})</div>
                  <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                    {companyRoles.map(r => (
                      <div key={r.id} onClick={() => onOpenRole && onOpenRole(r)} style={{
                        display:"flex", alignItems:"center", gap:8, padding:"8px 10px",
                        background:"#F7F7F8", borderRadius:6, cursor:"pointer", fontSize:12,
                      }}
                        onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                        onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                        <TierPill tier={r.tier} />
                        <span style={{ fontWeight:600, color:"#1A1A1A", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{cleanTitle(r.title)}</span>
                        <Score v={r.final_score ?? r.rule_score} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : role && detailTab === "contacts" && role.hiring_manager_name ? (
            <>
              {/* Hiring Manager Details */}
              <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12 }}>Hiring Manager</div>
              <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"8px 12px", fontSize:12 }}>
                {[
                  ["Name", role.hiring_manager_name || "—"],
                  ["Title", role.hiring_manager_title || "—"],
                  ["LinkedIn", role.hiring_manager_linkedin],
                  ["Confidence", null],
                  ["DM", "Yes"],
                ].map(([label, value]) => {
                  let rendered = value || "—";
                  if (label === "LinkedIn" && value) rendered = <a href={value} target="_blank" rel="noopener" style={{ fontSize:12, color:"#0A66C2", textDecoration:"none", fontWeight:600 }}>Profile ↗</a>;
                  else if (label === "Confidence" && role.hiring_manager_confidence) rendered = <span style={{ padding:"2px 6px", borderRadius:3, fontSize:11, fontWeight:600, background: role.hiring_manager_confidence === "high" ? "#D1FAE5" : role.hiring_manager_confidence === "medium" ? "#FEF3C7" : "#F2F3F5", color: role.hiring_manager_confidence === "high" ? "#065F46" : role.hiring_manager_confidence === "medium" ? "#92400E" : "#6B6F76" }}>{role.hiring_manager_confidence}</span>;
                  else if (label === "DM") rendered = <span style={{ fontSize:11, fontWeight:700, padding:"2px 6px", borderRadius:3, background:"#FDECEC", color:"#C13030" }}>Decision Maker</span>;
                  return (
                    <div key={label} style={{ display:"contents" }}>
                      <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                      <div style={{ color:"#1A1A1A" }}>{rendered}</div>
                    </div>
                  );
                })}
              </div>

              {/* Outreach Tracking Summary */}
              <div style={{ marginTop:20, paddingTop:16, borderTop:"1px solid #EBEBED" }}>
                <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:10 }}>Outreach Status</div>
                <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"6px 12px", fontSize:12 }}>
                  <div style={{ color:"#A0A3A9" }}>Sequence</div>
                  <div style={{ color:"#1A1A1A", fontWeight:600 }}>Step 2 of 4</div>
                  <div style={{ color:"#A0A3A9" }}>Opens</div>
                  <div style={{ color:"#1A1A1A" }}>3 total</div>
                  <div style={{ color:"#A0A3A9" }}>Bounced</div>
                  <div style={{ color:"#065F46" }}>No</div>
                  <div style={{ color:"#A0A3A9" }}>Last Activity</div>
                  <div style={{ color:"#1A1A1A" }}>4 Mar 2026</div>
                  <div style={{ color:"#A0A3A9" }}>Sentiment</div>
                  <div><span style={{ padding:"2px 8px", borderRadius:4, fontSize:10, fontWeight:600, background:"#D1FAE5", color:"#065F46" }}>interested</span></div>
                </div>
              </div>

              {/* Company section */}
              {company && (
                <div style={{ marginTop:28, paddingTop:20, borderTop:"1px solid #EBEBED" }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12 }}>Company</div>
                  <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"8px 12px", fontSize:12 }}>
                    {[
                      ["Name", company.name],
                      ["Domain", company.domain || "—"],
                      ["Industry", company.industry || "—"],
                      ["Fit", company.arteq_fit],
                      ["Funding", company.funding_stage && company.funding_stage !== "unknown" ? company.funding_stage : "—"],
                      ["Headcount", company.headcount || "—"],
                      ["HQ", company.hq_city || "—"],
                    ].map(([label, value]) => {
                      let rendered = value || "—";
                      if (label === "Fit" && value && fitColors[value]) {
                        rendered = <span style={{ padding:"2px 6px", borderRadius:3, fontSize:11, fontWeight:500, background:fitColors[value].bg, color:fitColors[value].color }}>{value}</span>;
                      }
                      return (
                        <div key={label} style={{ display:"contents" }}>
                          <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                          <div style={{ color:"#1A1A1A" }}>{rendered}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Open roles at this company */}
              {companyRoles.length > 0 && (
                <div style={{ marginTop:20, paddingTop:16, borderTop:"1px solid #EBEBED" }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:10 }}>Open Roles ({companyRoles.length})</div>
                  <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                    {companyRoles.map(r => (
                      <div key={r.id} onClick={() => onOpenRole && onOpenRole(r)} style={{
                        display:"flex", alignItems:"center", gap:8, padding:"8px 10px",
                        background:"#F7F7F8", borderRadius:6, cursor:"pointer", fontSize:12,
                      }}
                        onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                        onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                        <TierPill tier={r.tier} />
                        <span style={{ fontWeight:600, color:"#1A1A1A", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{cleanTitle(r.title)}</span>
                        <Score v={r.final_score ?? r.rule_score} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : role ? (
            <>
              {/* Role Details */}
              <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12 }}>Role Details</div>
              <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"8px 12px", fontSize:12 }}>
                {[
                  ["Tier", null],
                  ["Score", role.final_score ?? role.qualification_score ?? role.rule_score ?? "—"],
                  ["Type", null],
                  ["Source", null],
                  ["Location", cleanLocation(role.location)],
                  ["Remote", role.is_remote ? "Yes" : "No"],
                  ["Status", role.status || "—"],
                  ["Posted", role.posted_at ? new Date(role.posted_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : "—"],
                  ["Job Posting", null],
                ].map(([label, value]) => {
                  let rendered = value || "—";
                  if (label === "Tier") rendered = role.tier || "—";
                  else if (label === "Type") rendered = role.engagement_type || "—";
                  else if (label === "Source") rendered = role.source || "—";
                  else if (label === "Job Posting") rendered = role.source_url
                    ? <a href={role.source_url} target="_blank" rel="noopener" style={{ color:"#0A66C2", textDecoration:"none", fontSize:12 }}>View posting ↗</a>
                    : "—";
                  return (
                    <div key={label} style={{ display:"contents" }}>
                      <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                      <div style={{ color:"#1A1A1A", fontSize:12 }}>{rendered}</div>
                    </div>
                  );
                })}
              </div>

              {role.signals && role.signals.length > 0 && (
                <div style={{ marginTop:14 }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:6 }}>Signals</div>
                  <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                    {role.signals.map((s,i) => <span key={i} style={{ padding:"2px 8px", borderRadius:4, fontSize:11, background:"#F2F3F5", color:"#6B6F76" }}>{s}</span>)}
                  </div>
                </div>
              )}

              {role.url && (
                <a href={role.url} target="_blank" rel="noopener" style={{
                  display:"inline-flex", alignItems:"center", gap:5,
                  marginTop:22, padding:"8px 16px", borderRadius:6,
                  background:"#1A1A1A", color:"#fff", fontSize:12, fontWeight:600,
                  textDecoration:"none",
                }}>View job posting ↗</a>
              )}

              {/* Other roles at this company */}
              {(() => {
                const siblingRoles = companyRoles.filter(r => r.id !== role.id);
                if (siblingRoles.length === 0) return null;
                return (
                  <div style={{ marginTop:20, paddingTop:16, borderTop:"1px solid #EBEBED" }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:10 }}>Other roles at {company.name}</div>
                    <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                      {siblingRoles.map(r => (
                        <div key={r.id} onClick={() => onOpenRole && onOpenRole(r)} style={{
                          display:"flex", alignItems:"center", gap:8, padding:"8px 10px",
                          background:"#F7F7F8", borderRadius:6, cursor:"pointer", fontSize:12,
                        }}
                          onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                          onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                          <TierPill tier={r.tier} />
                          <span style={{ fontWeight:600, color:"#1A1A1A", flex:1 }}>{cleanTitle(r.title)}</span>
                          <Score v={r.final_score ?? r.rule_score} />
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </>
          ) : (
            <>
              {/* Company Details — Grouped Sections */}

              {/* Score + Status header */}
              <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16, flexWrap:"wrap" }}>
                <span style={{ padding:"3px 10px", borderRadius:4, fontSize:12, fontWeight:600, background:statusStyle.bg, color:statusStyle.color }}>{company.status || "—"}</span>
                {company.arteq_fit && fitColors[company.arteq_fit] && (
                  <span style={{ padding:"3px 10px", borderRadius:4, fontSize:12, fontWeight:600, background:fitColors[company.arteq_fit].bg, color:fitColors[company.arteq_fit].color }}>{company.arteq_fit} fit</span>
                )}
                {company.composite_score != null && (
                  <span style={{ padding:"3px 10px", borderRadius:4, fontSize:12, fontWeight:600, background:"#F2F3F5", color:"#1A1A1A" }}>Score: {company.composite_score}</span>
                )}
              </div>

              {/* Overview */}
              <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:8 }}>Overview</div>
              <div style={{ display:"grid", gridTemplateColumns:"90px 1fr", gap:"6px 12px", fontSize:12, marginBottom:18 }}>
                {[
                  ["Domain", company.domain ? <a href={`https://${company.domain}`} target="_blank" rel="noopener" style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{company.domain} ↗</a> : "—"],
                  ["Industry", company.industry || "—"],
                  ["HQ", company.hq_city || "—"],
                  ["Founded", company.founded_year || "—"],
                  ["Headcount", company.headcount || "—"],
                ].map(([label, value]) => (
                  <div key={label} style={{ display:"contents" }}>
                    <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                    <div style={{ color:"#1A1A1A" }}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Business */}
              <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:8 }}>Business</div>
              <div style={{ display:"grid", gridTemplateColumns:"90px 1fr", gap:"6px 12px", fontSize:12, marginBottom:18 }}>
                {[
                  ["Funding", [company.funding_stage, company.funding_amount].filter(x => x && x !== "unknown").join(" — ") || "—"],
                  ["Investors", company.investors || "—"],
                  ["Revenue", company.revenue || "—"],
                ].map(([label, value]) => (
                  <div key={label} style={{ display:"contents" }}>
                    <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                    <div style={{ color:"#1A1A1A" }}>{value || "—"}</div>
                  </div>
                ))}
              </div>

              {/* Pipeline */}
              <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:8 }}>Pipeline</div>
              <div style={{ display:"grid", gridTemplateColumns:"90px 1fr", gap:"6px 12px", fontSize:12, marginBottom:18 }}>
                {(() => {
                  const pBg = {"sdr_outreach":"#DBEAFE","sdr_followup":"#DBEAFE","qualified":"#D1FAE5","meeting_prep":"#FEF3C7","meeting_done":"#FEF3C7","proposal":"#EDE9FE","closed_won":"#D1FAE5","closed_lost":"#FDECEC","nurture":"#F2F3F5"}[company.pipeline_stage] || "#F2F3F5";
                  const pColor = {"sdr_outreach":"#1D4ED8","sdr_followup":"#1D4ED8","qualified":"#065F46","meeting_prep":"#92400E","meeting_done":"#92400E","proposal":"#6D28D9","closed_won":"#065F46","closed_lost":"#C13030","nurture":"#6B6F76"}[company.pipeline_stage] || "#6B6F76";
                  return [
                    ["Pipeline", company.pipeline_stage ? <span style={{ padding:"2px 6px", borderRadius:3, fontSize:11, fontWeight:600, background:pBg, color:pColor }}>{company.pipeline_stage.replace(/_/g," ")}</span> : "—"],
                    ["Agent", company.agent_owner || "—"],
                    ["Added", company.created_at ? new Date(company.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : "—"],
                  ].map(([label, value]) => (
                    <div key={label} style={{ display:"contents" }}>
                      <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                      <div style={{ color:"#1A1A1A" }}>{value || "—"}</div>
                    </div>
                  ));
                })()}
              </div>

              {/* Enrich Button */}
              <button
                onClick={handleEnrich}
                disabled={enriching}
                style={{
                  marginTop:20, width:"100%", padding:"10px 16px", borderRadius:8,
                  border: enriching ? "1px solid #EBEBED" : "1px solid #5B5FC7",
                  background: enriching ? "#F7F7F8" : "#5B5FC7",
                  color: enriching ? "#A0A3A9" : "#fff",
                  fontSize:13, fontWeight:600, cursor: enriching ? "default" : "pointer",
                  fontFamily:"inherit", display:"flex", alignItems:"center", justifyContent:"center", gap:8,
                }}
              >
                {enriching ? "Enriching..." : "Enrich with AI"}
              </button>

              {/* Roles at this company */}
              {companyRoles.length > 0 && (
                <div style={{ marginTop:20, paddingTop:16, borderTop:"1px solid #EBEBED" }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:10 }}>Roles ({companyRoles.length})</div>
                  <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                    {companyRoles.map(r => (
                      <div key={r.id} onClick={() => onOpenRole && onOpenRole(r)} style={{
                        display:"flex", alignItems:"center", gap:8, padding:"8px 10px",
                        background:"#F7F7F8", borderRadius:6, cursor:"pointer", fontSize:12,
                      }}
                        onMouseEnter={e => e.currentTarget.style.background="#EBEBED"}
                        onMouseLeave={e => e.currentTarget.style.background="#F7F7F8"}>
                        <TierPill tier={r.tier} />
                        <span style={{ fontWeight:600, color:"#1A1A1A", flex:1, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{cleanTitle(r.title)}</span>
                        <Score v={r.final_score ?? r.rule_score} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ALineCRM() {
  const [roles, setRoles] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState({});  // company_id → primary contact
  const [allContacts, setAllContacts] = useState({});  // company_id → [contacts]
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("roles");
  const [tierFilter, setTierFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key:"final_score", dir:"desc" });
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [selectedCompanyIndex, setSelectedCompanyIndex] = useState(-1);
  const [selectedRole, setSelectedRole] = useState(null);
  const [selectedRoleIndex, setSelectedRoleIndex] = useState(-1);
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [selectedPersonIndex, setSelectedPersonIndex] = useState(-1);
  const [allPeopleList, setAllPeopleList] = useState([]);
  const [allCandidatesList, setAllCandidatesList] = useState([]);
  const [agencies, setAgencies] = useState([]);
  const [agencyFilter, setAgencyFilter] = useState("all");
  const [selectedAgency, setSelectedAgency] = useState(null);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [agencyContacts, setAgencyContacts] = useState([]);
  const [agencyDetailTab, setAgencyDetailTab] = useState("summary");
  const [showAgencyContactForm, setShowAgencyContactForm] = useState(false);
  const [newAgencyContact, setNewAgencyContact] = useState({ name:"", title:"", email:"", linkedin_url:"", is_primary:false });
  const [savingAgencyContact, setSavingAgencyContact] = useState(false);
  const cMap = useRef({});

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [c, r, cc, candidates, ag] = await Promise.all([
        supaFetch("company","select=*&limit=1000"),
        supaFetch("role","select=*&limit=1000"),
        supaFetch("contact","select=*&limit=2000").catch(() => []),
        supaFetch("candidate","select=*&limit=1000").catch(() => []),
        supaFetch("agency","select=*&order=quality_score.desc.nullslast,created_at.desc&limit=500").catch(() => []),
      ]);
      setAgencies(ag || []);
      setAllCandidatesList(candidates || []);
      setCompanies(c);
      const m = {}; c.forEach(co => { m[co.id] = co; }); cMap.current = m;
      setRoles(r);
      // Build company_id → contact maps (primary + all)
      // cc is now a flat array of contacts with company_id, first_name, last_name
      const dmMap = {};
      const allMap = {};
      const pList = [];
      (cc || []).forEach(ct => {
        const name = [ct.first_name, ct.last_name].filter(Boolean).join(" ") || ct.email || "?";
        const enriched = { ...ct, name, role_at_company: ct.title, is_decision_maker: ct.is_primary };
        if (ct.company_id) {
          if (ct.is_primary && !dmMap[ct.company_id]) dmMap[ct.company_id] = enriched;
          if (!allMap[ct.company_id]) allMap[ct.company_id] = [];
          allMap[ct.company_id].push(enriched);
        }
        pList.push(enriched);
      });
      // Merge hiring manager flags from roles into existing contacts (dedup)
      (r || []).forEach(role => {
        if (!role.hiring_manager_name) return;
        const co = m[role.company_id];
        // Check if this HM already exists as a real contact (match by name+company, name without company, or LinkedIn URL)
        const hmNameLower = role.hiring_manager_name?.toLowerCase();
        const hmLinkedin = role.hiring_manager_linkedin?.replace(/\/+$/, "").toLowerCase();
        const existingIdx = pList.findIndex(p =>
          !p._isHiringManager && (
            (p.company_id === role.company_id && p.name?.toLowerCase() === hmNameLower) ||
            (!p.company_id && p.name?.toLowerCase() === hmNameLower) ||
            (hmLinkedin && p.linkedin_url && p.linkedin_url.replace(/\/+$/, "").toLowerCase() === hmLinkedin)
          )
        );
        if (existingIdx >= 0) {
          // Merge HM flags into existing real contact
          pList[existingIdx] = {
            ...pList[existingIdx],
            _isHiringManager: true,
            _roleId: role.id,
            is_decision_maker: true,
            linkedin_url: pList[existingIdx].linkedin_url || role.hiring_manager_linkedin,
          };
        } else {
          pList.push({
            id: `hm_${role.id}`,
            name: role.hiring_manager_name,
            title: role.hiring_manager_title,
            role_at_company: role.hiring_manager_title,
            linkedin_url: role.hiring_manager_linkedin,
            is_decision_maker: true,
            is_primary: true,
            source: "role_enricher",
            company_id: role.company_id,
            company_name: co?.name,
            _isHiringManager: true,
            _roleId: role.id,
          });
        }
        // Also add to allMap so they appear in company contacts tab
        if (role.company_id) {
          if (!allMap[role.company_id]) allMap[role.company_id] = [];
          const alreadyExists = allMap[role.company_id].some(c =>
            c.name?.toLowerCase() === role.hiring_manager_name?.toLowerCase()
          );
          if (!alreadyExists) {
            allMap[role.company_id].push({
              id: `hm_${role.id}`,
              name: role.hiring_manager_name,
              title: role.hiring_manager_title,
              role_at_company: role.hiring_manager_title,
              linkedin_url: role.hiring_manager_linkedin,
              is_decision_maker: true,
              is_primary: true,
              source: "role_enricher",
              company_id: role.company_id,
              _isHiringManager: true,
            });
          }
        }
      });
      setContacts(dmMap);
      setAllContacts(allMap);
      setAllPeopleList(pList);
    } catch(e) { setError(e.message); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const tierCounts = {};
  roles.forEach(r => { tierCounts[r.tier] = (tierCounts[r.tier]||0)+1; });
  const sources = [...new Set(roles.map(r=>r.source).filter(Boolean))];

  const filtered = roles.filter(r => {
    if (tierFilter !== "all" && r.tier !== tierFilter) return false;
    if (sourceFilter !== "all" && r.source !== sourceFilter) return false;
    if (search) {
      const co = cMap.current[r.company_id];
      if (!`${r.title} ${co?.name||""} ${r.location||""}`.toLowerCase().includes(search.toLowerCase())) return false;
    }
    return true;
  }).sort((a,b) => {
    let av = a[sort.key], bv = b[sort.key];
    if (av==null) av = sort.dir==="desc" ? -Infinity : Infinity;
    if (bv==null) bv = sort.dir==="desc" ? -Infinity : Infinity;
    if (typeof av === "string") { av = av.toLowerCase(); bv = (bv||"").toLowerCase(); }
    return av < bv ? (sort.dir==="asc"?-1:1) : av > bv ? (sort.dir==="asc"?1:-1) : 0;
  });

  const doSort = k => setSort(p => p.key===k ? {key:k,dir:p.dir==="asc"?"desc":"asc"} : {key:k,dir:"desc"});

  const filteredCompanies = companies;
  const filteredPeople = allPeopleList;

  // Talent pool filtering
  const CAND_TIER = {
    available: { label:"Available", bg:"#D1FAE5", color:"#065F46" },
    passive:   { label:"Passive",   bg:"#FFF0E1", color:"#AD5700" },
    research:  { label:"Research",  bg:"#EDE9FE", color:"#6D28D9" },
  };

  const filteredCandidates = allCandidatesList.filter(c => {
    if (search && !`${c.full_name||""} ${c.current_title||""} ${c.location||""} ${c.source||""}`.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const navigateCompany = useCallback((direction) => {
    if (selectedRole) {
      const newIndex = selectedRoleIndex + direction;
      if (newIndex >= 0 && newIndex < filtered.length) {
        const r = filtered[newIndex];
        setSelectedRoleIndex(newIndex);
        setSelectedRole(r);
        setSelectedCompany(cMap.current[r.company_id] || selectedCompany);
      }
    }
  }, [selectedRole, selectedRoleIndex, filtered, selectedCompany]);

  const closeDetail = useCallback(() => {
    setSelectedCompany(null); setSelectedCompanyIndex(-1);
    setSelectedRole(null); setSelectedRoleIndex(-1);
    setSelectedPerson(null); setSelectedPersonIndex(-1);
  }, []);

  useEffect(() => {
    if (!selectedCompany && !selectedAgency && !selectedCandidate) return;
    const handler = (e) => {
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Escape") { closeDetail(); setSelectedAgency(null); setAgencyContacts([]); setSelectedCandidate(null); }
      if (selectedCompany) {
        if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); navigateCompany(-1); }
        if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); navigateCompany(1); }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedCompany, selectedAgency, selectedCandidate, navigateCompany, closeDetail]);

  return (
    <div style={{ display:"flex", height:"100vh", overflow:"hidden", fontFamily:"'Inter',-apple-system,BlinkMacSystemFont,sans-serif", background:"#fff", color:"#1A1A1A", fontSize:13 }}>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />

      {/* ── Sidebar ── */}
      <div style={{ width:210, borderRight:"1px solid #EBEBED", padding:"16px 10px", display:"flex", flexDirection:"column", background:"#FAFAFA", flexShrink:0, overflowY:"auto", overflowX:"hidden" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 10px", marginBottom:28 }}>
          <div style={{ width:24, height:24, borderRadius:6, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontWeight:800, fontSize:12 }}>A</div>
          <span style={{ fontWeight:700, fontSize:15, letterSpacing:-0.5 }}>A-Line</span>
        </div>

        <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"0 10px", marginBottom:8 }}>Demand Side</div>

        <div onClick={() => { setTab("roles"); setSearch(""); setTierFilter("all"); setSourceFilter("all"); setSelectedCompany(null); setSelectedCompanyIndex(-1); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); setSelectedAgency(null); setAgencyContacts([]); setSelectedCandidate(null); }} style={{
          display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
          background:tab==="roles"?"#EBEBED":"transparent", color:tab==="roles"?"#1A1A1A":"#6B6F76",
          fontSize:13, fontWeight:tab==="roles"?600:400, cursor:"pointer", marginBottom:1,
        }}>
          <span style={{ fontSize:14, width:18, textAlign:"center", opacity:0.6 }}>⊙</span>
          <span style={{ flex:1 }}>Roles</span>
          <span style={{ fontSize:11, color:"#A0A3A9" }}>{roles.length}</span>
        </div>

        <div style={{ height:12 }} />
        <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"0 10px", marginBottom:8 }}>Supply Side</div>

        <div onClick={() => { setTab("agencies"); setSearch(""); setAgencyFilter("all"); setSelectedCompany(null); setSelectedCompanyIndex(-1); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); setSelectedAgency(null); setAgencyContacts([]); setSelectedCandidate(null); }} style={{
          display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
          background:tab==="agencies"?"#EBEBED":"transparent", color:tab==="agencies"?"#1A1A1A":"#6B6F76",
          fontSize:13, fontWeight:tab==="agencies"?600:400, cursor:"pointer", marginBottom:1,
        }}>
          <span style={{ fontSize:14, width:18, textAlign:"center", opacity:0.6 }}>◆</span>
          <span style={{ flex:1 }}>Agencies</span>
          <span style={{ fontSize:11, color:"#A0A3A9" }}>{agencies.length || null}</span>
        </div>

        <div onClick={() => { setTab("talent"); setSearch(""); setSelectedCompany(null); setSelectedCompanyIndex(-1); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); setSelectedAgency(null); setAgencyContacts([]); setSelectedCandidate(null); }} style={{
          display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
          background:tab==="talent"?"#EBEBED":"transparent", color:tab==="talent"?"#1A1A1A":"#6B6F76",
          fontSize:13, fontWeight:tab==="talent"?600:400, cursor:"pointer", marginBottom:1,
        }}>
          <span style={{ fontSize:14, width:18, textAlign:"center", opacity:0.6 }}>⊘</span>
          <span style={{ flex:1 }}>Talent Pool</span>
          <span style={{ fontSize:11, color:"#A0A3A9" }}>{allCandidatesList.length || null}</span>
        </div>

        <div style={{ flex:1 }} />
        <div style={{ padding:"12px 10px", borderTop:"1px solid #EBEBED" }}>
          <div style={{ fontSize:11, color:"#A0A3A9" }}>Supabase</div>
          <div style={{ fontSize:12, fontWeight:500, color:error?"#E5484D":loading?"#A0A3A9":"#30A46C", marginTop:2 }}>
            {error ? "Error" : loading ? "Loading…" : "Connected"}
          </div>
        </div>
      </div>

      {/* ── Main ── */}
      <div style={{ flex:1, display:"flex", flexDirection:"column", minWidth:0 }}>

        {selectedCompany ? (
          <CompanyDetailView key={selectedPerson ? `person-${selectedPerson.id}` : selectedRole ? `role-${selectedRole.id}` : selectedCompany.id} company={selectedCompany} contacts={allContacts[selectedCompany.id] || []} onClose={closeDetail} onContactsChanged={load} currentIndex={selectedRole ? selectedRoleIndex : selectedCompanyIndex} totalCount={selectedRole ? filtered.length : 0} onNavigate={navigateCompany} tabLabel="Roles" role={selectedRole} person={selectedPerson} companyRoles={roles.filter(r => r.company_id === selectedCompany.id)} onOpenRole={(r) => { const co = cMap.current[r.company_id]; if (co) { setSelectedCompany(co); setSelectedCompanyIndex(companies.indexOf(co)); } setSelectedRole(r); setSelectedRoleIndex(filtered.indexOf(r)); setSelectedPerson(null); setSelectedPersonIndex(-1); }} onOpenPerson={(p) => { const co = cMap.current[p.company_id]; if (co) { setSelectedCompany(co); setSelectedCompanyIndex(companies.indexOf(co)); } setSelectedPerson(p); setSelectedPersonIndex(allPeopleList.indexOf(p)); setSelectedRole(null); setSelectedRoleIndex(-1); }} onOpenCompany={(co) => { setSelectedCompany(co); setSelectedCompanyIndex(companies.indexOf(co)); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); }} />
        ) : selectedAgency ? (
          /* ── Full-screen Agency Detail ── */
          <div style={{ flex:1, display:"flex", flexDirection:"column", minWidth:0, minHeight:0, fontFamily:"'Inter',-apple-system,sans-serif" }}>
            {/* Top Bar */}
            <div style={{ padding:"10px 20px", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", gap:12 }}>
              <button onClick={() => { setSelectedAgency(null); setAgencyContacts([]); setSelectedCandidate(null); }} style={{
                width:28, height:28, borderRadius:6, border:"1px solid #EBEBED",
                background:"#fff", cursor:"pointer", fontSize:15, color:"#6B6F76",
                display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
              }}>×</button>
              <div style={{ width:1, height:20, background:"#EBEBED" }} />
              <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A" }}>{selectedAgency.name}</div>
              {selectedAgency.domain && (
                <a href={`https://${selectedAgency.domain}`} target="_blank" rel="noopener" style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{selectedAgency.domain} ↗</a>
              )}
            </div>
            {/* Two-Column Body */}
            <div style={{ flex:1, display:"flex", overflow:"hidden" }}>
              {/* LEFT — Tabbed Content */}
              <div style={{ flex:3, display:"flex", flexDirection:"column", borderRight:"1px solid #EBEBED", minHeight:0 }}>

                {/* Sub-nav tabs */}
                <div style={{ display:"flex", gap:0, borderBottom:"1px solid #EBEBED", padding:"0 24px", flexShrink:0 }}>
                  {[
                    { key:"summary", label:"Summary" },
                    { key:"contacts", label:"Contacts", count: agencyContacts.length },
                    { key:"candidates", label:"Candidates", count: 0 },
                  ].map(t => {
                    const active = agencyDetailTab === t.key;
                    return (
                      <button key={t.key} onClick={() => setAgencyDetailTab(t.key)} style={{
                        padding:"10px 16px", fontSize:12, fontWeight:active ? 600 : 400, cursor:"pointer",
                        border:"none", borderBottom: active ? "2px solid #1A1A1A" : "2px solid transparent",
                        background:"transparent", color: active ? "#1A1A1A" : "#A0A3A9",
                        fontFamily:"inherit", marginBottom:-1,
                      }}>{t.label}{t.count != null ? ` (${t.count})` : ""}</button>
                    );
                  })}
                </div>

                {/* Tab content */}
                <div style={{ flex:1, overflow:"auto", padding:"20px 24px" }}>

                  {/* ── Agency Summary Tab ── */}
                  {agencyDetailTab === "summary" && (
                    <div>
                      {/* Description */}
                      {selectedAgency.description && (
                        <div style={{ fontSize:13, color:"#1A1A1A", lineHeight:1.7, marginBottom:20, padding:"14px 18px", background:"#EDE9FE", borderRadius:10, border:"1px solid #DDD6FE", fontWeight:500 }}>
                          {selectedAgency.description}
                        </div>
                      )}

                      {/* Quality Assessment */}
                      {selectedAgency.quality_reason && (
                        <div style={{ marginBottom:20 }}>
                          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
                            <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5 }}>Quality Assessment</div>
                            {selectedAgency.quality_score != null && (
                              <span style={{ padding:"2px 8px", borderRadius:4, fontSize:11, fontWeight:700, background:"#F2F3F5", color:"#1A1A1A" }}>{selectedAgency.quality_score}/10</span>
                            )}
                          </div>
                          <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, padding:"10px 14px", background:"#F7F7F8", borderRadius:6 }}>
                            {selectedAgency.quality_reason}
                          </div>
                        </div>
                      )}

                      {/* Competitor Assessment */}
                      {selectedAgency.is_direct_competitor_reason && (
                        <div style={{ marginBottom:20 }}>
                          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
                            <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5 }}>Competitor Assessment</div>
                            {selectedAgency.is_direct_competitor && (
                              <span style={{ padding:"2px 8px", borderRadius:4, fontSize:11, fontWeight:700, background:"#FDECEC", color:"#C13030" }}>Competitor</span>
                            )}
                          </div>
                          <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, padding:"10px 14px", background:"#FEF2F2", borderRadius:6, border:"1px solid #FECACA" }}>
                            {selectedAgency.is_direct_competitor_reason}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* ── Agency Contacts Tab ── */}
                  {agencyDetailTab === "contacts" && (
                    <div>
                      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
                        <div style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>
                          {agencyContacts.length} {agencyContacts.length === 1 ? "contact" : "contacts"}
                        </div>
                        <button onClick={() => setShowAgencyContactForm(!showAgencyContactForm)} style={{
                          padding:"5px 14px", borderRadius:6, fontSize:12, fontWeight:600, cursor:"pointer",
                          border:"1px solid #EBEBED", background: showAgencyContactForm ? "#1A1A1A" : "#fff",
                          color: showAgencyContactForm ? "#fff" : "#6B6F76", fontFamily:"inherit",
                        }}>{showAgencyContactForm ? "Cancel" : "+ Add Contact"}</button>
                      </div>

                      {showAgencyContactForm && (
                        <div style={{ background:"#FAFAFA", borderRadius:8, padding:16, marginBottom:16, border:"1px solid #EBEBED" }}>
                          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                            <input value={newAgencyContact.name} onChange={e => setNewAgencyContact(p => ({...p, name: e.target.value}))} placeholder="Name *" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none", gridColumn:"1 / -1" }} />
                            <input value={newAgencyContact.title} onChange={e => setNewAgencyContact(p => ({...p, title: e.target.value}))} placeholder="Title" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                            <input value={newAgencyContact.email} onChange={e => setNewAgencyContact(p => ({...p, email: e.target.value}))} placeholder="Email" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                            <input value={newAgencyContact.linkedin_url} onChange={e => setNewAgencyContact(p => ({...p, linkedin_url: e.target.value}))} placeholder="LinkedIn URL" style={{ padding:"8px 10px", borderRadius:6, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                            <label style={{ display:"flex", alignItems:"center", gap:6, fontSize:12, color:"#6B6F76", cursor:"pointer" }}>
                              <input type="checkbox" checked={newAgencyContact.is_primary} onChange={e => setNewAgencyContact(p => ({...p, is_primary: e.target.checked}))} />
                              Primary contact (GF)
                            </label>
                          </div>
                          <button onClick={async () => {
                            if (!newAgencyContact.name.trim()) return;
                            setSavingAgencyContact(true);
                            try {
                              await supaPost("agency_contact", {
                                agency_id: selectedAgency.id,
                                name: newAgencyContact.name.trim(),
                                title: newAgencyContact.title.trim() || null,
                                email: newAgencyContact.email.trim() || null,
                                linkedin_url: newAgencyContact.linkedin_url.trim() || null,
                                is_primary: newAgencyContact.is_primary,
                              });
                              setNewAgencyContact({ name:"", title:"", email:"", linkedin_url:"", is_primary:false });
                              setShowAgencyContactForm(false);
                              const contacts = await supaFetch("agency_contact", `agency_id=eq.${selectedAgency.id}&order=is_primary.desc`);
                              setAgencyContacts(contacts || []);
                            } catch (e) {
                              alert("Could not save contact: " + e.message);
                            }
                            setSavingAgencyContact(false);
                          }} disabled={savingAgencyContact || !newAgencyContact.name.trim()} style={{
                            marginTop:10, padding:"7px 18px", borderRadius:6, border:"none", fontSize:12, fontWeight:600, cursor: newAgencyContact.name.trim() ? "pointer" : "default", fontFamily:"inherit",
                            background: newAgencyContact.name.trim() ? "#1A1A1A" : "#EBEBED", color: newAgencyContact.name.trim() ? "#fff" : "#A0A3A9",
                          }}>{savingAgencyContact ? "Saving..." : "Save Contact"}</button>
                        </div>
                      )}

                      {agencyContacts.length === 0 ? (
                        <div style={{ fontSize:12, color:"#A0A3A9", padding:16, textAlign:"center" }}>No contacts found yet</div>
                      ) : (
                        <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                          {agencyContacts.map((c, i) => (
                            <div key={c.id || i} style={{ display:"flex", alignItems:"center", gap:12, padding:"12px 14px", background:"#F7F7F8", borderRadius:10 }}>
                              <div style={{ width:36, height:36, borderRadius:8, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", fontSize:14, fontWeight:700, color:"#fff", flexShrink:0 }}>
                                {c.name?.charAt(0) || "?"}
                              </div>
                              <div style={{ flex:1, minWidth:0 }}>
                                <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                                  <span style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>{c.name}</span>
                                  {c.is_primary && <span style={{ fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3, background:"#FEF3C7", color:"#92400E" }}>GF</span>}
                                  {c.confidence && (
                                    <span style={{ fontSize:9, fontWeight:600, padding:"1px 5px", borderRadius:3,
                                      background: c.confidence==="high"?"#D1FAE5":c.confidence==="medium"?"#FEF3C7":"#F2F3F5",
                                      color: c.confidence==="high"?"#065F46":c.confidence==="medium"?"#92400E":"#6B6F76",
                                    }}>{c.confidence}</span>
                                  )}
                                </div>
                                <div style={{ fontSize:11, color:"#6B6F76", marginTop:1 }}>{c.title || ""}</div>
                                <div style={{ display:"flex", gap:8, marginTop:4, flexWrap:"wrap" }}>
                                  {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noopener" style={{ fontSize:11, color:"#0A66C2", textDecoration:"none", fontWeight:600 }}>LinkedIn</a>}
                                  {c.email && <a href={`mailto:${c.email}`} style={{ fontSize:11, color:"#5B5FC7", textDecoration:"none" }}>{c.email}</a>}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Email Feed for Agency Contacts */}
                      <EmailFeed emails={PLACEHOLDER_EMAILS_AGENCY} entityName={agencyContacts[0]?.name || "Agency Contact"} />
                    </div>
                  )}

                  {/* ── Agency Candidates Tab ── */}
                  {agencyDetailTab === "candidates" && (
                    <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
                      <div style={{ fontSize:22, marginBottom:6 }}>⊙</div>
                      <div style={{ fontSize:13, fontWeight:500 }}>Coming soon</div>
                      <div style={{ fontSize:12, marginTop:4 }}>Agency candidate tracking will appear here.</div>
                    </div>
                  )}
                </div>
              </div>

              {/* RIGHT — Agency Details */}
              <div style={{ flex:2, overflow:"auto", padding:"20px 24px" }}>
                {/* Status badges */}
                <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:20 }}>
                  {selectedAgency.is_direct_competitor && (
                    <span style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:600, background:"#FDECEC", color:"#C13030" }}>Competitor</span>
                  )}
                  <span style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:500, background: selectedAgency.enrichment_status==="enriched"?"#D1FAE5":"#FEF3C7", color: selectedAgency.enrichment_status==="enriched"?"#065F46":"#92400E" }}>
                    {selectedAgency.enrichment_status || "pending"}
                  </span>
                  {selectedAgency.quality_score != null && (
                    <span style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:600, background:"#F2F3F5", color:"#1A1A1A" }}>Quality: {selectedAgency.quality_score}/10</span>
                  )}
                </div>

                {/* Overview */}
                <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:8 }}>Overview</div>
                <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"6px 12px", fontSize:12, marginBottom:18 }}>
                  {[
                    ["Location", [selectedAgency.hq_city, selectedAgency.hq_country].filter(Boolean).join(", ")],
                    ["Headcount", selectedAgency.headcount],
                    ["Founded", selectedAgency.founded_year],
                    ["Geo Focus", selectedAgency.geographic_focus],
                    ["Source", selectedAgency.source],
                    ["Outreach", selectedAgency.outreach_status || "pending"],
                    ["Added", selectedAgency.created_at ? new Date(selectedAgency.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : null],
                  ].map(([label, value]) => (
                    <div key={label} style={{ display:"contents" }}>
                      <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                      <div style={{ color:"#1A1A1A" }}>{value || "—"}</div>
                    </div>
                  ))}
                </div>

                {/* Specialization */}
                {selectedAgency.specialization && selectedAgency.specialization.length > 0 && (
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:6 }}>Specialization</div>
                    <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                      {selectedAgency.specialization.map((s, i) => (
                        <span key={i} style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:500, background:"#EDE9FE", color:"#6D28D9" }}>{s}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : selectedCandidate ? (
          /* ── Full-screen Candidate Detail ── */
          <div style={{ flex:1, display:"flex", flexDirection:"column", minWidth:0, minHeight:0, fontFamily:"'Inter',-apple-system,sans-serif" }}>
            {/* Top Bar */}
            <div style={{ padding:"10px 20px", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", gap:12 }}>
              <button onClick={() => setSelectedCandidate(null)} style={{
                width:28, height:28, borderRadius:6, border:"1px solid #EBEBED",
                background:"#fff", cursor:"pointer", fontSize:15, color:"#6B6F76",
                display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
              }}>×</button>
              <div style={{ width:1, height:20, background:"#EBEBED" }} />
              <div style={{ fontSize:15, fontWeight:700, color:"#1A1A1A" }}>{selectedCandidate.full_name}</div>
              {selectedCandidate.linkedin_url && (
                <a href={selectedCandidate.linkedin_url} target="_blank" rel="noopener" style={{ padding:"3px 8px", borderRadius:4, background:"#0A66C2", color:"#fff", fontSize:10, fontWeight:600, textDecoration:"none" }}>in</a>
              )}
            </div>
            {/* Two-Column Body */}
            <div style={{ flex:1, display:"flex", overflow:"hidden" }}>
              {/* LEFT — Summary */}
              <div style={{ flex:3, overflow:"auto", padding:"20px 24px", borderRight:"1px solid #EBEBED" }}>
                {/* Bio / Summary */}
                {selectedCandidate.summary && (
                  <div style={{ fontSize:13, color:"#1A1A1A", lineHeight:1.7, marginBottom:20, padding:"14px 18px", background:"#EDE9FE", borderRadius:10, border:"1px solid #DDD6FE", fontWeight:500 }}>
                    {selectedCandidate.summary}
                  </div>
                )}

                {/* Skills */}
                {selectedCandidate.skills && selectedCandidate.skills.length > 0 && (
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Skills</div>
                    <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
                      {selectedCandidate.skills.map((s, i) => (
                        <span key={i} style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:500, background:"#F2F3F5", color:"#6B6F76" }}>{s}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Experience */}
                {selectedCandidate.experience_summary && (
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Experience</div>
                    <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, padding:"10px 14px", background:"#F7F7F8", borderRadius:6 }}>
                      {selectedCandidate.experience_summary}
                    </div>
                  </div>
                )}

                {/* Notes */}
                {selectedCandidate.notes && (
                  <div style={{ marginBottom:20 }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Notes</div>
                    <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, padding:"10px 14px", background:"#F7F7F8", borderRadius:6 }}>
                      {selectedCandidate.notes}
                    </div>
                  </div>
                )}

                {/* Email Feed for candidate */}
                <div style={{ marginBottom:20 }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.5, marginBottom:8 }}>Outreach</div>
                  <EmailFeed emails={PLACEHOLDER_EMAILS_CANDIDATE} entityName={selectedCandidate.full_name} />
                </div>
              </div>

              {/* RIGHT — Details */}
              <div style={{ flex:2, overflow:"auto", padding:"20px 24px" }}>
                {/* Tier + Score badges */}
                <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:20 }}>
                  {(() => { const t = CAND_TIER[selectedCandidate.tier] || { label:selectedCandidate.tier||"—", bg:"#F2F3F5", color:"#6B6F76" }; return (
                    <span style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:600, background:t.bg, color:t.color }}>{t.label}</span>
                  ); })()}
                  {selectedCandidate.score != null && (
                    <span style={{ padding:"3px 10px", borderRadius:4, fontSize:11, fontWeight:600, background:"#F2F3F5", color:"#1A1A1A" }}>Score: {selectedCandidate.score}</span>
                  )}
                </div>

                {/* Overview */}
                <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:8 }}>Overview</div>
                <div style={{ display:"grid", gridTemplateColumns:"100px 1fr", gap:"6px 12px", fontSize:12, marginBottom:18 }}>
                  {[
                    ["Name", selectedCandidate.full_name],
                    ["Title", selectedCandidate.current_title],
                    ["Email", selectedCandidate.email],
                    ["Phone", selectedCandidate.phone],
                    ["LinkedIn", selectedCandidate.linkedin_url],
                    ["Location", selectedCandidate.location],
                    ["Source", selectedCandidate.source],
                    ["Added", selectedCandidate.created_at ? new Date(selectedCandidate.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : null],
                  ].map(([label, value]) => {
                    let rendered = value || "—";
                    if (label === "Email" && value) rendered = <a href={`mailto:${value}`} style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{value}</a>;
                    else if (label === "LinkedIn" && value) rendered = <a href={value} target="_blank" rel="noopener" style={{ fontSize:12, color:"#0A66C2", textDecoration:"none", fontWeight:600 }}>Profile ↗</a>;
                    else if (label === "Source") rendered = <SourcePill source={value} />;
                    return (
                      <div key={label} style={{ display:"contents" }}>
                        <div style={{ color:"#A0A3A9", fontSize:12 }}>{label}</div>
                        <div style={{ color:"#1A1A1A" }}>{rendered}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        ) : (
        <>
        {/* Topbar */}
        <div style={{ padding:"12px 20px", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontSize:15, fontWeight:600 }}>{tab === "roles" ? "Roles" : tab === "agencies" ? "Agencies" : "Talent Pool"}</span>
            <span style={{ fontSize:12, color:"#A0A3A9" }}>{tab === "roles" ? `${filtered.length} records` : tab === "agencies" ? `${agencies.length} agencies` : `${filteredCandidates.length} candidates`}</span>
          </div>
          <button onClick={load} style={{
            padding:"5px 12px", borderRadius:6, border:"1px solid #EBEBED",
            background:"#fff", cursor:"pointer", fontSize:12, fontWeight:500,
            color:"#6B6F76", fontFamily:"inherit",
          }}>↻ Refresh</button>
        </div>

        {/* Filters */}
        {tab === "agencies" ? (
          /* ── Agencies filter bar ── */
          <div style={{ display:"flex", alignItems:"center", gap:5, padding:"8px 20px", borderBottom:"1px solid #EBEBED", flexWrap:"wrap" }}>
            {["all","enriched","pending"].map(s => {
              const cnt = s === "all" ? agencies.length : agencies.filter(a => a.enrichment_status === s).length;
              return (
                <button key={s} onClick={() => setAgencyFilter(s)} style={{
                  padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                  border: agencyFilter===s ? "1.5px solid #1A1A1A" : "1px solid #EBEBED",
                  background: agencyFilter===s ? "#1A1A1A" : "#fff",
                  color: agencyFilter===s ? "#fff" : "#6B6F76", fontFamily:"inherit",
                }}>{s === "all" ? `All ${cnt}` : `${s} ${cnt}`}</button>
              );
            })}
          </div>
        ) : tab === "talent" ? (
          /* ── Talent Pool filter bar ── */
          <div style={{ display:"flex", alignItems:"center", gap:5, padding:"8px 20px", borderBottom:"1px solid #EBEBED", flexWrap:"wrap" }}>
            <div style={{ flex:1 }} />
            <div style={{ position:"relative" }}>
              <span style={{ position:"absolute", left:9, top:"50%", transform:"translateY(-50%)", fontSize:12, color:"#A0A3A9" }}>⌕</span>
              <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter…" style={{
                padding:"5px 10px 5px 26px", borderRadius:6, border:"1px solid #EBEBED",
                fontSize:12, fontFamily:"inherit", outline:"none", width:170, color:"#1A1A1A",
              }} />
            </div>
          </div>
        ) : (
          /* ── Roles filter bar ── */
          <div style={{ display:"flex", alignItems:"center", gap:5, padding:"8px 20px", borderBottom:"1px solid #EBEBED", flexWrap:"wrap" }}>
            {["all",...Object.keys(tierCounts)].map(t => (
              <button key={t} onClick={() => setTierFilter(t)} style={{
                padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                border: tierFilter===t ? "1.5px solid #1A1A1A" : "1px solid #EBEBED",
                background: tierFilter===t ? "#1A1A1A" : "#fff",
                color: tierFilter===t ? "#fff" : "#6B6F76",
              }}>
                {t==="all" ? `All ${roles.length}` : `${TIER[t]?.label||t} ${tierCounts[t]}`}
              </button>
            ))}
            {sources.length > 0 && <div style={{ width:1, height:18, background:"#EBEBED", margin:"0 4px" }} />}
            {sources.map(s => (
              <button key={s} onClick={() => setSourceFilter(sourceFilter===s?"all":s)} style={{
                padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                border: sourceFilter===s ? "1.5px solid #5B5FC7" : "1px solid #EBEBED",
                background: sourceFilter===s ? "#5B5FC7" : "#fff",
                color: sourceFilter===s ? "#fff" : "#6B6F76",
              }}>{s}</button>
            ))}
            <div style={{ flex:1 }} />
            <div style={{ position:"relative" }}>
              <span style={{ position:"absolute", left:9, top:"50%", transform:"translateY(-50%)", fontSize:12, color:"#A0A3A9" }}>⌕</span>
              <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter…" style={{
                padding:"5px 10px 5px 26px", borderRadius:6, border:"1px solid #EBEBED",
                fontSize:12, fontFamily:"inherit", outline:"none", width:170, color:"#1A1A1A",
              }} />
            </div>
          </div>
        )}

        {/* Table */}
        <div style={{ flex:1, overflow:"auto" }}>
          {loading ? (
            <div style={{ padding:60, textAlign:"center", color:"#A0A3A9", fontSize:14 }}>Loading…</div>
          ) : tab === "roles" ? (
            filtered.length === 0 ? (
              <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                <div style={{ fontSize:26, marginBottom:6 }}>∅</div>
                <div style={{ fontSize:14, fontWeight:500 }}>No roles yet</div>
                <div style={{ fontSize:12, marginTop:4 }}>Run the scraper to populate records.</div>
              </div>
            ) : (
              <table style={{ width:"100%", borderCollapse:"collapse", tableLayout:"fixed" }}>
                <thead>
                  <tr>
                    <ColHead width="11.1%" sk="tier" sort={sort} onSort={doSort}>Tier</ColHead>
                    <ColHead width="11.1%" align="center" sk="final_score" sort={sort} onSort={doSort}>Score</ColHead>
                    <ColHead width="11.1%" sk="company_id" sort={sort} onSort={doSort}>Company</ColHead>
                    <ColHead width="11.1%" sk="title" sort={sort} onSort={doSort}>Title</ColHead>
                    <ColHead width="11.1%">Location</ColHead>
                    <ColHead width="11.1%">Source</ColHead>
                    <ColHead width="11.1%">Decision Maker</ColHead>
                    <ColHead width="11.1%">Type</ColHead>
                    <ColHead width="11.1%" sk="posted_at" sort={sort} onSort={doSort}>Posted</ColHead>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0,200).map(r => {
                    const co = cMap.current[r.company_id];
                    return (
                      <tr key={r.id} onClick={() => { const co = cMap.current[r.company_id]; if (co) { setSelectedCompany(co); setSelectedCompanyIndex(-1); setSelectedRole(r); setSelectedRoleIndex(filtered.indexOf(r)); } }} style={{ cursor:"pointer", borderBottom:"1px solid #F7F7F8" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}><TierPill tier={r.tier} /></td>
                        <td style={{ padding:"9px 14px", textAlign:"center" }}><Score v={r.final_score??r.rule_score} /></td>
                        <td style={{ padding:"9px 14px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                          <div style={{ fontWeight:600, fontSize:13, overflow:"hidden", textOverflow:"ellipsis" }}>{co?.name||"—"}</div>
                          {co?.is_agency && <span style={{ fontSize:10, color:"#E5484D", fontWeight:500 }}>Agency</span>}
                        </td>
                        <td style={{ padding:"9px 14px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                          <div style={{ fontWeight:500, overflow:"hidden", textOverflow:"ellipsis" }}>{cleanTitle(r.title)}</div>
                          {r.requirements_summary && <div style={{ fontSize:11, color:"#A0A3A9", lineHeight:1.3, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.requirements_summary}</div>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{cleanLocation(r.location)}</td>
                        <td style={{ padding:"9px 14px" }}><SourcePill source={r.source} /></td>
                        <td style={{ padding:"9px 14px" }}>
                          {(() => {
                            const dm = contacts[r.company_id];
                            const name = dm?.name || r.hiring_manager_name;
                            if (!name) return <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>;
                            const title = dm?.title || r.hiring_manager_title;
                            const url = dm?.linkedin_url || r.hiring_manager_linkedin;
                            return url
                              ? <a href={url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{ fontSize:12, fontWeight:600, color:"#1A1A1A", textDecoration:"none" }}>{name}</a>
                              : <span style={{ fontSize:12, fontWeight:600, color:"#1A1A1A" }}>{name}</span>;
                          })()}
                        </td>
                        <td style={{ padding:"9px 14px" }}><EngPill type={r.engagement_type} /></td>
                        <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                          {r.posted_at ? new Date(r.posted_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          ) : tab === "agencies" ? (
            (() => {
              const filteredAgencies = agencies.filter(a => {
                if (agencyFilter !== "all" && a.enrichment_status !== agencyFilter) return false;
                if (search && !`${a.name} ${a.domain} ${a.hq_city||""}`.toLowerCase().includes(search.toLowerCase())) return false;
                return true;
              });
              return filteredAgencies.length === 0 ? (
                <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                  <div style={{ fontSize:26, marginBottom:6 }}>∅</div>
                  <div style={{ fontSize:14, fontWeight:500 }}>No agencies yet</div>
                  <div style={{ fontSize:12, marginTop:4 }}>Run the agency finder to discover agencies.</div>
                </div>
              ) : (
                <table style={{ width:"100%", borderCollapse:"collapse", tableLayout:"fixed" }}>
                  <thead>
                    <tr>
                      <ColHead width="20%">Agency</ColHead>
                      <ColHead width="20%">Status</ColHead>
                      <ColHead width="20%">Location</ColHead>
                      <ColHead width="20%">Outreach</ColHead>
                      <ColHead width="20%">Added</ColHead>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAgencies.slice(0,200).map(a => (
                      <tr key={a.id} onClick={async () => {
                        setSelectedAgency(a);
                        setAgencyDetailTab("summary");
                        setShowAgencyContactForm(false);
                        try {
                          const contacts = await supaFetch("agency_contact", `agency_id=eq.${a.id}&order=is_primary.desc`);
                          setAgencyContacts(contacts || []);
                        } catch { setAgencyContacts([]); }
                      }} style={{ borderBottom:"1px solid #F7F7F8", cursor:"pointer" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:600, fontSize:13 }}>{a.name}</div>
                        </td>
                        <td style={{ padding:"9px 14px" }}>
                          <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background: a.enrichment_status==="enriched"?"#D1FAE5":"#FEF3C7", color: a.enrichment_status==="enriched"?"#065F46":"#92400E" }}>{a.enrichment_status || "pending"}</span>
                        </td>
                        <td style={{ padding:"9px 14px", fontSize:12, color:"#6B6F76" }}>{[a.hq_city, a.hq_country].filter(Boolean).join(", ") || "—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background:"#F2F3F5", color:"#6B6F76" }}>{a.outreach_status || "pending"}</span>
                        </td>
                        <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                          {a.created_at ? new Date(a.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              );
            })()
          ) : (
            /* ── Talent Pool table ── */
            filteredCandidates.length === 0 ? (
              <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                <div style={{ fontSize:26, marginBottom:6 }}>⊘</div>
                <div style={{ fontSize:14, fontWeight:500 }}>No candidates yet</div>
                <div style={{ fontSize:12, marginTop:4 }}>Run the candidate pipeline to discover talent.</div>
              </div>
            ) : (
              <table style={{ width:"100%", borderCollapse:"collapse", tableLayout:"fixed" }}>
                <thead>
                  <tr>
                    <ColHead width="20%">Name</ColHead>
                    <ColHead width="20%">Title</ColHead>
                    <ColHead width="10%">Tier</ColHead>
                    <ColHead width="8%" align="center">Score</ColHead>
                    <ColHead width="16%">Location</ColHead>
                    <ColHead width="12%">Source</ColHead>
                    <ColHead width="14%">Added</ColHead>
                  </tr>
                </thead>
                <tbody>
                  {filteredCandidates.slice(0,200).map(c => {
                    const tier = CAND_TIER[c.tier] || { label:c.tier||"—", bg:"#F2F3F5", color:"#6B6F76" };
                    return (
                      <tr key={c.id} onClick={() => setSelectedCandidate(c)} style={{ borderBottom:"1px solid #F7F7F8", cursor:"pointer" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                            <span style={{ fontWeight:600, fontSize:13 }}>{c.full_name || "—"}</span>
                            {c.linkedin_url && (
                              <a href={c.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{ padding:"2px 6px", borderRadius:4, background:"#0A66C2", color:"#fff", fontSize:9, fontWeight:600, textDecoration:"none" }}>in</a>
                            )}
                          </div>
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{c.current_title || "—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background:tier.bg, color:tier.color }}>{tier.label}</span>
                        </td>
                        <td style={{ padding:"9px 14px", textAlign:"center" }}><Score v={c.score} /></td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{c.location || "—"}</td>
                        <td style={{ padding:"9px 14px" }}><SourcePill source={c.source} /></td>
                        <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                          {c.created_at ? new Date(c.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          )}
        </div>
        </>
        )}
      </div>

    </div>
  );
}
