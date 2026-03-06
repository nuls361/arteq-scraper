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

async function supaPatch(table, match, data) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${match}`, {
    method: "PATCH",
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

function MatchScorePill({ score }) {
  if (score == null) return <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>;
  const bg = score >= 80 ? "#FDECEC" : score >= 60 ? "#FFF0E1" : "#F2F3F5";
  const color = score >= 80 ? "#C13030" : score >= 60 ? "#AD5700" : "#6B6F76";
  return <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:700, background:bg, color, fontVariantNumeric:"tabular-nums" }}>{score}</span>;
}

const MATCH_STATUS = {
  proposed: { bg:"#EDE9FE", color:"#6D28D9" },
  reviewed: { bg:"#DBEAFE", color:"#1D4ED8" },
  accepted: { bg:"#D1FAE5", color:"#065F46" },
  rejected: { bg:"#FDECEC", color:"#C13030" },
};

function MatchStatusPill({ status }) {
  const s = MATCH_STATUS[status] || { bg:"#F2F3F5", color:"#6B6F76" };
  return <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:600, background:s.bg, color:s.color, textTransform:"capitalize" }}>{status || "—"}</span>;
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
  agent_action:     { label: "Agent",          icon: "🤖", bg: "#EDE9FE", color: "#6D28D9" },
  outreach:         { label: "Outreach",       icon: "📨", bg: "#DBEAFE", color: "#1D4ED8" },
  role_analysis:    { label: "Role Analysis",  icon: "📋", bg: "#D1FAE5", color: "#065F46" },
  role_dm_research: { label: "Hiring Manager", icon: "🎯", bg: "#FEF3C7", color: "#92400E" },
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
  const [detailTab, setDetailTab] = useState("activity");
  const [enriching, setEnriching] = useState(false);
  const [companyAgentLogs, setCompanyAgentLogs] = useState([]);
  const [roleMatches, setRoleMatches] = useState([]);
  const [matchCandidates, setMatchCandidates] = useState({});
  const [expandedReasoning, setExpandedReasoning] = useState({});

  const loadEntries = useCallback(async () => {
    if (!company) return;
    setLoading(true);
    try {
      // When viewing a role, fetch role-specific dossier entries
      const params = role
        ? `role_id=eq.${role.id}&order=created_at.desc&limit=200`
        : `company_id=eq.${company.id}&order=created_at.desc&limit=200`;
      const data = await supaFetch("company_dossier", params);
      setEntries(data || []);
    } catch (e) {
      console.error("Dossier load error:", e);
    }
    setLoading(false);
  }, [company, role]);

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

  // Load candidate matches for this role
  useEffect(() => {
    if (!role) { setRoleMatches([]); setMatchCandidates({}); return; }
    (async () => {
      try {
        const matches = await supaFetch(
          "role_candidate_match",
          `role_id=eq.${role.id}&order=match_score.desc`
        );
        setRoleMatches(matches || []);
        const cIds = [...new Set((matches || []).map(m => m.candidate_id).filter(Boolean))];
        if (cIds.length > 0) {
          const cands = await supaFetch("candidate", `id=in.(${cIds.join(",")})`);
          const cm = {};
          (cands || []).forEach(c => { cm[c.id] = c; });
          setMatchCandidates(cm);
        }
      } catch (e) { console.error("Match load error:", e); }
    })();
  }, [role]);

  const updateMatchStatus = async (matchId, newStatus) => {
    try {
      await supaPatch("role_candidate_match", `id=eq.${matchId}`, { status: newStatus, updated_at: new Date().toISOString() });
      setRoleMatches(prev => prev.map(m => m.id === matchId ? { ...m, status: newStatus } : m));
    } catch (e) { console.error("Match status update error:", e); }
  };

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
      setDetailTab("activity");
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
      // Upload to Supabase Storage: dossier-files/{company_id}/{timestamp}_{filename}
      const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
      const storagePath = `${company.id}/${Date.now()}_${safeName}`;
      const publicUrl = await supaUploadFile("dossier-files", storagePath, file);

      // Create dossier entry for the file
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
            {[
              { key:"activity", label: role ? "Analysis" : "Dossier", count:timelineItems.length },
              { key:"contacts", label: role ? "Hiring Manager" : "Contacts", count:contacts.length },
              { key:"candidates", label:"Candidates", count:0 },
            ].map(t => {
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

            {/* ── Activity Tab ── */}
            {detailTab === "activity" && (
              <>
                {/* Company Summary Card */}
                {!person && !role && company && (
                  <div style={{ background:"#F7F7F8", borderRadius:10, padding:"16px 18px", marginBottom:20 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:10 }}>
                      <div style={{ width:36, height:36, borderRadius:8, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontWeight:800, fontSize:15, flexShrink:0 }}>
                        {company.name?.charAt(0) || "?"}
                      </div>
                      <div>
                        <div style={{ fontSize:14, fontWeight:700, color:"#1A1A1A" }}>{company.name}</div>
                        <div style={{ fontSize:11, color:"#6B6F76" }}>
                          {[company.industry, company.hq_city, company.headcount ? `~${company.headcount} employees` : null].filter(Boolean).join(" · ") || "—"}
                        </div>
                      </div>
                    </div>
                    <div style={{ display:"flex", gap:6, flexWrap:"wrap" }}>
                      {company.funding_stage && company.funding_stage !== "unknown" && (
                        <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background:"#DBEAFE", color:"#1D4ED8" }}>{company.funding_stage}</span>
                      )}
                      {company.composite_score != null && (
                        <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background:"#F2F3F5", color:"#1A1A1A" }}>Score: {company.composite_score}</span>
                      )}
                      {companyRoles.length > 0 && (
                        <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background:"#EDE9FE", color:"#6D28D9" }}>{companyRoles.length} {companyRoles.length === 1 ? "role" : "roles"}</span>
                      )}
                      {contacts.length > 0 && (
                        <span style={{ padding:"3px 8px", borderRadius:4, fontSize:11, fontWeight:500, background:"#D1FAE5", color:"#065F46" }}>{contacts.length} {contacts.length === 1 ? "contact" : "contacts"}</span>
                      )}
                    </div>
                  </div>
                )}
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

                      // Dossier entry
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
                              <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6 }}
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
                          <a href={role.hiring_manager_linkedin} target="_blank" rel="noopener" style={{
                            padding:"6px 14px", borderRadius:6, background:"#0A66C2", color:"#fff",
                            fontSize:12, fontWeight:600, textDecoration:"none", display:"inline-flex", alignItems:"center", gap:4,
                          }}>LinkedIn Profile</a>
                        )}
                      </div>
                    </div>
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

              {role.requirements_summary && (
                <div style={{ marginTop:18 }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:6 }}>Requirements</div>
                  <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, background:"#F7F7F8", padding:"10px 12px", borderRadius:6, whiteSpace:"pre-wrap" }}>{role.requirements_summary}</div>
                </div>
              )}

              {role.engagement_reasoning && (
                <div style={{ marginTop:14 }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:6 }}>Reasoning</div>
                  <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, background:"#F7F7F8", padding:"10px 12px", borderRadius:6, whiteSpace:"pre-wrap" }}>{role.engagement_reasoning}</div>
                </div>
              )}

              {role.outreach_angle && (
                <div style={{ marginTop:14 }}>
                  <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:6 }}>Outreach Angle</div>
                  <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, background:"#F7F7F8", padding:"10px 12px", borderRadius:6, whiteSpace:"pre-wrap" }}>{role.outreach_angle}</div>
                </div>
              )}

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

              {/* Sourcing Brief */}
              {(() => {
                const brief = typeof role.sourcing_brief === "string" ? (() => { try { return JSON.parse(role.sourcing_brief); } catch { return null; } })() : role.sourcing_brief;
                if (!brief) return null;
                return (
                  <div style={{ marginTop:28, paddingTop:20, borderTop:"1px solid #EBEBED" }}>
                    <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12 }}>Sourcing Brief</div>

                    {brief.must_have && brief.must_have.length > 0 && (
                      <div style={{ marginBottom:14 }}>
                        <div style={{ fontSize:11, fontWeight:600, color:"#065F46", marginBottom:6 }}>Must-Have</div>
                        <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
                          {brief.must_have.map((item, i) => (
                            <div key={i} style={{ fontSize:11, color:"#1A1A1A", padding:"4px 8px", background:"#D1FAE5", borderRadius:4 }}>{item}</div>
                          ))}
                        </div>
                      </div>
                    )}

                    {brief.nice_to_have && brief.nice_to_have.length > 0 && (
                      <div style={{ marginBottom:14 }}>
                        <div style={{ fontSize:11, fontWeight:600, color:"#AD5700", marginBottom:6 }}>Nice-to-Have</div>
                        <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
                          {brief.nice_to_have.map((item, i) => (
                            <div key={i} style={{ fontSize:11, color:"#1A1A1A", padding:"4px 8px", background:"#FFF0E1", borderRadius:4 }}>{item}</div>
                          ))}
                        </div>
                      </div>
                    )}

                    {brief.ideal_candidate_profile && (
                      <div style={{ marginBottom:14 }}>
                        <div style={{ fontSize:11, fontWeight:600, color:"#6D28D9", marginBottom:6 }}>Ideal Profile</div>
                        <div style={{ fontSize:11, color:"#6B6F76", background:"#F7F7F8", padding:"8px 10px", borderRadius:6, lineHeight:1.5 }}>
                          {brief.ideal_candidate_profile.background && <div><strong>Background:</strong> {brief.ideal_candidate_profile.background}</div>}
                          {brief.ideal_candidate_profile.years_experience && <div><strong>Experience:</strong> {brief.ideal_candidate_profile.years_experience}</div>}
                          {brief.ideal_candidate_profile.titles_to_search && <div><strong>Target titles:</strong> {brief.ideal_candidate_profile.titles_to_search.join(", ")}</div>}
                        </div>
                      </div>
                    )}

                    {brief.linkedin_boolean_search && (
                      <div style={{ marginBottom:14 }}>
                        <div style={{ fontSize:11, fontWeight:600, color:"#1D4ED8", marginBottom:6 }}>LinkedIn Boolean Search</div>
                        <div style={{ fontSize:11, color:"#1D4ED8", background:"#DBEAFE", padding:"8px 10px", borderRadius:6, fontFamily:"monospace", wordBreak:"break-all" }}>{brief.linkedin_boolean_search}</div>
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Candidate Matches */}
              <div style={{ marginTop:28, paddingTop:20, borderTop:"1px solid #EBEBED" }}>
                <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, marginBottom:12 }}>
                  Candidate Matches {roleMatches.length > 0 && `(${roleMatches.length})`}
                </div>
                {roleMatches.length === 0 ? (
                  <div style={{ fontSize:12, color:"#A0A3A9", padding:"12px 0" }}>
                    {role.research_status === "pending" || role.research_status === "running" ? "Research pending…" : "No candidate matches yet"}
                  </div>
                ) : (
                  <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                    {roleMatches.map(match => {
                      const cand = matchCandidates[match.candidate_id] || {};
                      const expanded = expandedReasoning[match.id];
                      return (
                        <div key={match.id} style={{ border:"1px solid #EBEBED", borderRadius:8, padding:"12px 14px", background:"#FAFAFA" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
                            <div style={{ flex:1, minWidth:0 }}>
                              <div style={{ fontWeight:600, fontSize:13, color:"#1A1A1A" }}>{cand.full_name || "Unknown"}</div>
                              {cand.current_title && <div style={{ fontSize:11, color:"#6B6F76", marginTop:1 }}>{cand.current_title}</div>}
                            </div>
                            <MatchScorePill score={match.match_score} />
                          </div>

                          <div style={{ display:"flex", gap:4, flexWrap:"wrap", marginBottom:8 }}>
                            {match.function_match && <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:600, background:"#D1FAE5", color:"#065F46" }}>Function ✓</span>}
                            {match.location_match && <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:600, background:"#D1FAE5", color:"#065F46" }}>Location ✓</span>}
                            {!match.function_match && <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:500, background:"#F2F3F5", color:"#A0A3A9" }}>Function ✗</span>}
                            {!match.location_match && <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:500, background:"#F2F3F5", color:"#A0A3A9" }}>Location ✗</span>}
                          </div>

                          {match.skills_overlap && match.skills_overlap.length > 0 && (
                            <div style={{ display:"flex", gap:3, flexWrap:"wrap", marginBottom:8 }}>
                              {match.skills_overlap.map((s,i) => <span key={i} style={{ padding:"2px 6px", borderRadius:3, fontSize:10, background:"#EDE9FE", color:"#6D28D9" }}>{s}</span>)}
                            </div>
                          )}

                          {match.match_reasoning && (
                            <div style={{ marginBottom:8 }}>
                              <div onClick={() => setExpandedReasoning(prev => ({ ...prev, [match.id]: !prev[match.id] }))} style={{ fontSize:11, color:"#5B5FC7", cursor:"pointer", userSelect:"none" }}>
                                {expanded ? "▾ Hide reasoning" : "▸ Show reasoning"}
                              </div>
                              {expanded && <div style={{ fontSize:11, color:"#6B6F76", lineHeight:1.5, marginTop:4, background:"#F7F7F8", padding:"8px 10px", borderRadius:4, whiteSpace:"pre-wrap" }}>{match.match_reasoning}</div>}
                            </div>
                          )}

                          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                            <select value={match.status || "proposed"} onChange={e => updateMatchStatus(match.id, e.target.value)} style={{
                              padding:"4px 8px", borderRadius:4, border:"1px solid #EBEBED", fontSize:11, fontFamily:"inherit", background:"#fff", cursor:"pointer",
                            }}>
                              <option value="proposed">Proposed</option>
                              <option value="reviewed">Reviewed</option>
                              <option value="accepted">Accepted</option>
                              <option value="rejected">Rejected</option>
                            </select>
                            {cand.linkedin_url && (
                              <a href={cand.linkedin_url} target="_blank" rel="noopener" style={{ padding:"3px 8px", borderRadius:4, background:"#0A66C2", color:"#fff", fontSize:10, fontWeight:600, textDecoration:"none" }}>LinkedIn</a>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Company section below role */}
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
                    if (label === "Name") rendered = <span onClick={() => onOpenCompany && onOpenCompany(company)} style={{ color:"#5B5FC7", cursor:"pointer", fontWeight:600 }}>{value} ↗</span>;
                    else if (label === "Fit" && value && fitColors[value]) {
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

              {company.description && (
                <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, marginBottom:18 }}>{company.description}</div>
              )}

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
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key:"final_score", dir:"desc" });
  const [selected, setSelected] = useState(null);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [selectedCompanyIndex, setSelectedCompanyIndex] = useState(-1);
  const [selectedRole, setSelectedRole] = useState(null);
  const [selectedRoleIndex, setSelectedRoleIndex] = useState(-1);
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [selectedPersonIndex, setSelectedPersonIndex] = useState(-1);
  const [agentLogs, setAgentLogs] = useState([]);
  const [allPeopleList, setAllPeopleList] = useState([]);
  const [peopleSourceFilter, setPeopleSourceFilter] = useState("all");
  const [peopleRoleTypeFilter, setPeopleRoleTypeFilter] = useState("all");
  const [allMatches, setAllMatches] = useState([]);
  const [allCandidates, setAllCandidates] = useState({});
  const [matchStatusFilter, setMatchStatusFilter] = useState("all");
  const cMap = useRef({});

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [c, r, cc, logs, matches, candidates] = await Promise.all([
        supaFetch("company","select=*&limit=1000"),
        supaFetch("role","select=*&limit=1000"),
        supaFetch("contact","select=*&limit=2000").catch(() => []),
        supaFetch("agent_log","select=*&order=created_at.desc&limit=200").catch(() => []),
        supaFetch("role_candidate_match","select=*&order=created_at.desc&limit=500").catch(() => []),
        supaFetch("candidate","select=*&limit=1000").catch(() => []),
      ]);
      setAgentLogs(logs || []);
      setAllMatches(matches || []);
      const candMap = {};
      (candidates || []).forEach(cd => { candMap[cd.id] = cd; });
      setAllCandidates(candMap);
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

  // Company filtering
  const STATUS = {
    lead:     { label:"Lead",     bg:"#EDE9FE", color:"#6D28D9" },
    prospect: { label:"Prospect", bg:"#DBEAFE", color:"#1D4ED8" },
    active:   { label:"Active",   bg:"#D1FAE5", color:"#065F46" },
    client:   { label:"Client",   bg:"#D1FAE5", color:"#047857" },
    churned:  { label:"Churned",  bg:"#FDECEC", color:"#C13030" },
  };
  const statusCounts = {};
  companies.forEach(c => { statusCounts[c.status] = (statusCounts[c.status]||0)+1; });

  const filteredCompanies = companies.filter(c => {
    if (statusFilter !== "all" && c.status !== statusFilter) return false;
    if (search && !`${c.name} ${c.industry||""} ${c.domain||""}`.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }).sort((a,b) => {
    let av = a[sort.key], bv = b[sort.key];
    if (av==null) av = sort.dir==="desc" ? -Infinity : Infinity;
    if (bv==null) bv = sort.dir==="desc" ? -Infinity : Infinity;
    if (typeof av === "string") { av = av.toLowerCase(); bv = (bv||"").toLowerCase(); }
    return av < bv ? (sort.dir==="asc"?-1:1) : av > bv ? (sort.dir==="asc"?1:-1) : 0;
  });

  // People filtering
  const peopleSourceCounts = {};
  allPeopleList.forEach(p => { peopleSourceCounts[p.source] = (peopleSourceCounts[p.source]||0)+1; });
  const peopleRoleTypes = {};
  allPeopleList.forEach(p => {
    const rt = p.role_type || (p.is_decision_maker ? "decision_maker" : null);
    if (rt) peopleRoleTypes[rt] = (peopleRoleTypes[rt]||0)+1;
  });

  const filteredPeople = allPeopleList.filter(p => {
    if (peopleSourceFilter !== "all" && p.source !== peopleSourceFilter) return false;
    if (peopleRoleTypeFilter !== "all") {
      const rt = p.role_type || (p.is_decision_maker ? "decision_maker" : null);
      if (rt !== peopleRoleTypeFilter) return false;
    }
    if (search) {
      const co = cMap.current[p.company_id];
      if (!`${p.name||""} ${p.title||""} ${p.role_at_company||""} ${co?.name||""} ${p.email||""}`.toLowerCase().includes(search.toLowerCase())) return false;
    }
    return true;
  }).sort((a,b) => {
    let av = a[sort.key], bv = b[sort.key];
    if (sort.key === "company_name") {
      av = cMap.current[a.company_id]?.name || "";
      bv = cMap.current[b.company_id]?.name || "";
    }
    if (av==null) av = sort.dir==="desc" ? -Infinity : Infinity;
    if (bv==null) bv = sort.dir==="desc" ? -Infinity : Infinity;
    if (typeof av === "string") { av = av.toLowerCase(); bv = (bv||"").toLowerCase(); }
    return av < bv ? (sort.dir==="asc"?-1:1) : av > bv ? (sort.dir==="asc"?1:-1) : 0;
  });

  const navigateCompany = useCallback((direction) => {
    if (selectedPerson) {
      const newIndex = selectedPersonIndex + direction;
      if (newIndex >= 0 && newIndex < filteredPeople.length) {
        const p = filteredPeople[newIndex];
        setSelectedPersonIndex(newIndex);
        setSelectedPerson(p);
        setSelectedCompany(cMap.current[p.company_id] || selectedCompany);
      }
    } else if (selectedRole) {
      const newIndex = selectedRoleIndex + direction;
      if (newIndex >= 0 && newIndex < filtered.length) {
        const r = filtered[newIndex];
        setSelectedRoleIndex(newIndex);
        setSelectedRole(r);
        setSelectedCompany(cMap.current[r.company_id] || selectedCompany);
      }
    } else {
      const newIndex = selectedCompanyIndex + direction;
      if (newIndex >= 0 && newIndex < filteredCompanies.length) {
        setSelectedCompanyIndex(newIndex);
        setSelectedCompany(filteredCompanies[newIndex]);
      }
    }
  }, [selectedCompanyIndex, filteredCompanies, selectedRole, selectedRoleIndex, filtered, selectedCompany, selectedPerson, selectedPersonIndex, filteredPeople]);

  const closeDetail = useCallback(() => {
    setSelectedCompany(null); setSelectedCompanyIndex(-1);
    setSelectedRole(null); setSelectedRoleIndex(-1);
    setSelectedPerson(null); setSelectedPersonIndex(-1);
  }, []);

  useEffect(() => {
    if (!selectedCompany) return;
    const handler = (e) => {
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Escape") closeDetail();
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); navigateCompany(-1); }
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); navigateCompany(1); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedCompany, navigateCompany, closeDetail]);

  return (
    <div style={{ display:"flex", height:"100vh", overflow:"hidden", fontFamily:"'Inter',-apple-system,BlinkMacSystemFont,sans-serif", background:"#fff", color:"#1A1A1A", fontSize:13 }}>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />

      {/* ── Sidebar ── */}
      <div style={{ width:210, borderRight:"1px solid #EBEBED", padding:"16px 10px", display:"flex", flexDirection:"column", background:"#FAFAFA", flexShrink:0, overflow:"hidden" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 10px", marginBottom:28 }}>
          <div style={{ width:24, height:24, borderRadius:6, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontWeight:800, fontSize:12 }}>A</div>
          <span style={{ fontWeight:700, fontSize:15, letterSpacing:-0.5 }}>A-Line</span>
        </div>

        <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"0 10px", marginBottom:8 }}>Pipeline</div>

        {[
          { icon:"○", label:"Companies", count:companies.length, key:"companies" },
          { icon:"◉", label:"People", count:allPeopleList.length, key:"people" },
          { icon:"⊙", label:"Roles", count:roles.length, key:"roles" },
        ].map(n => (
          <div key={n.label} onClick={() => { setTab(n.key); setSearch(""); setTierFilter("all"); setSourceFilter("all"); setStatusFilter("all"); setPeopleSourceFilter("all"); setPeopleRoleTypeFilter("all"); setSelectedCompany(null); setSelectedCompanyIndex(-1); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); }} style={{
            display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
            background:tab===n.key?"#EBEBED":"transparent", color:tab===n.key?"#1A1A1A":"#6B6F76",
            fontSize:13, fontWeight:tab===n.key?600:400, cursor:"pointer", marginBottom:1,
          }}>
            <span style={{ fontSize:14, width:18, textAlign:"center", opacity:0.6 }}>{n.icon}</span>
            <span style={{ flex:1 }}>{n.label}</span>
            <span style={{ fontSize:11, color:"#A0A3A9" }}>{n.count}</span>
          </div>
        ))}

        <div style={{ height:20 }} />
        <div key="Matches" onClick={() => { setTab("matches"); setSearch(""); setTierFilter("all"); setSourceFilter("all"); setStatusFilter("all"); setPeopleSourceFilter("all"); setPeopleRoleTypeFilter("all"); setMatchStatusFilter("all"); setSelectedCompany(null); setSelectedCompanyIndex(-1); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); }} style={{
          display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
          background:tab==="matches"?"#EBEBED":"transparent", color:tab==="matches"?"#1A1A1A":"#6B6F76",
          fontSize:13, fontWeight:tab==="matches"?600:400, cursor:"pointer", marginBottom:1,
        }}>
          <span style={{ fontSize:14, width:18, textAlign:"center", opacity:0.6 }}>◇</span>
          <span style={{ flex:1 }}>Matches</span>
          {allMatches.length > 0 && <span style={{ fontSize:11, color:"#A0A3A9" }}>{allMatches.length}</span>}
        </div>
        <div key="Agent Log" onClick={() => { setTab("agent"); setSearch(""); setTierFilter("all"); setSourceFilter("all"); setStatusFilter("all"); setPeopleSourceFilter("all"); setPeopleRoleTypeFilter("all"); setSelectedCompany(null); setSelectedCompanyIndex(-1); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); }} style={{
          display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
          background:tab==="agent"?"#EBEBED":"transparent", color:tab==="agent"?"#1A1A1A":"#6B6F76",
          fontSize:13, fontWeight:tab==="agent"?600:400, cursor:"pointer", marginBottom:1,
        }}>
          <span style={{ fontSize:14, width:18, textAlign:"center", opacity:0.6 }}>◎</span>
          <span style={{ flex:1 }}>Agent Log</span>
          <span style={{ fontSize:11, color:"#A0A3A9" }}>{agentLogs.length || null}</span>
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
          <CompanyDetailView key={selectedPerson ? `person-${selectedPerson.id}` : selectedRole ? `role-${selectedRole.id}` : selectedCompany.id} company={selectedCompany} contacts={allContacts[selectedCompany.id] || []} onClose={closeDetail} onContactsChanged={load} currentIndex={selectedPerson ? selectedPersonIndex : selectedRole ? selectedRoleIndex : selectedCompanyIndex} totalCount={selectedPerson ? filteredPeople.length : selectedRole ? filtered.length : filteredCompanies.length} onNavigate={navigateCompany} tabLabel={selectedPerson ? "People" : selectedRole ? "Roles" : tab === "companies" ? "Companies" : "People"} role={selectedRole} person={selectedPerson} companyRoles={roles.filter(r => r.company_id === selectedCompany.id)} onOpenRole={(r) => { const co = cMap.current[r.company_id]; if (co) { setSelectedCompany(co); setSelectedCompanyIndex(filteredCompanies.indexOf(co)); } setSelectedRole(r); setSelectedRoleIndex(filtered.indexOf(r)); setSelectedPerson(null); setSelectedPersonIndex(-1); }} onOpenPerson={(p) => { const co = cMap.current[p.company_id]; if (co) { setSelectedCompany(co); setSelectedCompanyIndex(filteredCompanies.indexOf(co)); } setSelectedPerson(p); setSelectedPersonIndex(filteredPeople.indexOf(p)); setSelectedRole(null); setSelectedRoleIndex(-1); }} onOpenCompany={(co) => { setSelectedCompany(co); setSelectedCompanyIndex(filteredCompanies.indexOf(co)); setSelectedRole(null); setSelectedRoleIndex(-1); setSelectedPerson(null); setSelectedPersonIndex(-1); }} />
        ) : (
        <>
        {/* Topbar */}
        <div style={{ padding:"12px 20px", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontSize:15, fontWeight:600 }}>{tab === "roles" ? "Roles" : tab === "companies" ? "Companies" : tab === "people" ? "People" : tab === "matches" ? "Matches" : "Agent Log"}</span>
            <span style={{ fontSize:12, color:"#A0A3A9" }}>{tab === "roles" ? `${filtered.length} records` : tab === "companies" ? `${filteredCompanies.length} records` : tab === "people" ? `${filteredPeople.length} contacts` : tab === "matches" ? `${allMatches.length} matches` : `${agentLogs.length} decisions`}</span>
          </div>
          <button onClick={load} style={{
            padding:"5px 12px", borderRadius:6, border:"1px solid #EBEBED",
            background:"#fff", cursor:"pointer", fontSize:12, fontWeight:500,
            color:"#6B6F76", fontFamily:"inherit",
          }}>↻ Refresh</button>
        </div>

        {/* Filters */}
        {tab === "agent" || tab === "matches" ? (
          tab === "matches" ? (
            <div style={{ display:"flex", alignItems:"center", gap:5, padding:"8px 20px", borderBottom:"1px solid #EBEBED", flexWrap:"wrap" }}>
              {["all","proposed","reviewed","accepted","rejected"].map(s => {
                const cnt = s === "all" ? allMatches.length : allMatches.filter(m => m.status === s).length;
                return (
                  <button key={s} onClick={() => setMatchStatusFilter(s)} style={{
                    padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                    border: matchStatusFilter===s ? "1.5px solid #1A1A1A" : "1px solid #EBEBED",
                    background: matchStatusFilter===s ? "#1A1A1A" : "#fff",
                    color: matchStatusFilter===s ? "#fff" : "#6B6F76",
                  }}>
                    {s === "all" ? `All ${cnt}` : `${s.charAt(0).toUpperCase()+s.slice(1)} ${cnt}`}
                  </button>
                );
              })}
              <div style={{ flex:1 }} />
              <div style={{ position:"relative" }}>
                <span style={{ position:"absolute", left:9, top:"50%", transform:"translateY(-50%)", fontSize:12, color:"#A0A3A9" }}>⌕</span>
                <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter…" style={{
                  padding:"5px 10px 5px 26px", borderRadius:6, border:"1px solid #EBEBED",
                  fontSize:12, fontFamily:"inherit", outline:"none", width:170, color:"#1A1A1A",
                }} />
              </div>
            </div>
          ) : null
        ) : tab === "people" ? (
          <div style={{ display:"flex", alignItems:"center", gap:5, padding:"8px 20px", borderBottom:"1px solid #EBEBED", flexWrap:"wrap" }}>
            {["all",...Object.keys(peopleSourceCounts).filter(Boolean)].map(s => (
              <button key={s} onClick={() => setPeopleSourceFilter(s)} style={{
                padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                border: peopleSourceFilter===s ? "1.5px solid #1A1A1A" : "1px solid #EBEBED",
                background: peopleSourceFilter===s ? "#1A1A1A" : "#fff",
                color: peopleSourceFilter===s ? "#fff" : "#6B6F76",
              }}>
                {s==="all" ? `All ${allPeopleList.length}` : `${s} ${peopleSourceCounts[s]}`}
              </button>
            ))}
            {Object.keys(peopleRoleTypes).length > 0 && <div style={{ width:1, height:18, background:"#EBEBED", margin:"0 4px" }} />}
            {Object.entries(peopleRoleTypes).map(([rt, count]) => (
              <button key={rt} onClick={() => setPeopleRoleTypeFilter(peopleRoleTypeFilter===rt?"all":rt)} style={{
                padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                border: peopleRoleTypeFilter===rt ? "1.5px solid #5B5FC7" : "1px solid #EBEBED",
                background: peopleRoleTypeFilter===rt ? "#5B5FC7" : "#fff",
                color: peopleRoleTypeFilter===rt ? "#fff" : "#6B6F76",
              }}>{rt.replace(/_/g," ")} {count}</button>
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
        ) : tab === "roles" ? (
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
        ) : (
          <div style={{ display:"flex", alignItems:"center", gap:5, padding:"8px 20px", borderBottom:"1px solid #EBEBED", flexWrap:"wrap" }}>
            {["all",...Object.keys(statusCounts)].map(s => (
              <button key={s} onClick={() => setStatusFilter(s)} style={{
                padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                border: statusFilter===s ? "1.5px solid #1A1A1A" : "1px solid #EBEBED",
                background: statusFilter===s ? "#1A1A1A" : "#fff",
                color: statusFilter===s ? "#fff" : "#6B6F76",
              }}>
                {s==="all" ? `All ${companies.length}` : `${STATUS[s]?.label||s} ${statusCounts[s]}`}
              </button>
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
              <table style={{ width:"100%", borderCollapse:"collapse" }}>
                <thead>
                  <tr>
                    <ColHead width={80} sk="tier" sort={sort} onSort={doSort}>Tier</ColHead>
                    <ColHead width={54} align="center" sk="final_score" sort={sort} onSort={doSort}>Score</ColHead>
                    <ColHead width={170} sk="company_id" sort={sort} onSort={doSort}>Company</ColHead>
                    <ColHead sk="title" sort={sort} onSort={doSort}>Title</ColHead>
                    <ColHead width={140}>Location</ColHead>
                    <ColHead width={85}>Source</ColHead>
                    <ColHead width={160}>Decision Maker</ColHead>
                    <ColHead width={95}>Type</ColHead>
                    <ColHead width={80} sk="posted_at" sort={sort} onSort={doSort}>Posted</ColHead>
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
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:600, fontSize:13 }}>{co?.name||"—"}</div>
                          {co?.is_agency && <span style={{ fontSize:10, color:"#E5484D", fontWeight:500 }}>Agency</span>}
                        </td>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:500 }}>{cleanTitle(r.title)}</div>
                          {r.requirements_summary && <div style={{ fontSize:11, color:"#A0A3A9", lineHeight:1.3, maxWidth:300, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.requirements_summary}</div>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{cleanLocation(r.location)}</td>
                        <td style={{ padding:"9px 14px" }}><SourcePill source={r.source} /></td>
                        <td style={{ padding:"9px 14px" }}>
                          {(() => {
                            const dm = contacts[r.company_id];
                            if (!dm) return <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>;
                            return (
                              <div style={{ display:"flex", flexDirection:"column", gap:1 }}>
                                <a href={dm.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{ fontSize:12, fontWeight:600, color:"#1A1A1A", textDecoration:"none" }}>{dm.name}</a>
                                <span style={{ fontSize:10, color:"#A0A3A9" }}>{dm.title}</span>
                              </div>
                            );
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
          ) : tab === "people" ? (
            filteredPeople.length === 0 ? (
              <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                <div style={{ fontSize:26, marginBottom:6 }}>∅</div>
                <div style={{ fontSize:14, fontWeight:500 }}>No contacts yet</div>
                <div style={{ fontSize:12, marginTop:4 }}>Contacts appear when companies are enriched.</div>
              </div>
            ) : (
              <table style={{ width:"100%", borderCollapse:"collapse" }}>
                <thead>
                  <tr>
                    <ColHead sk="name" sort={sort} onSort={doSort}>Name</ColHead>
                    <ColHead width={160}>Title</ColHead>
                    <ColHead width={150} sk="company_name" sort={sort} onSort={doSort}>Company</ColHead>
                    <ColHead width={180}>Email</ColHead>
                    <ColHead width={110}>Phone</ColHead>
                    <ColHead width={70}>LinkedIn</ColHead>
                    <ColHead width={85}>Source</ColHead>
                    <ColHead width={80} sk="created_at" sort={sort} onSort={doSort}>Added</ColHead>
                  </tr>
                </thead>
                <tbody>
                  {filteredPeople.slice(0,200).map(p => {
                    const co = cMap.current[p.company_id];
                    return (
                      <tr key={`${p.id}-${p.company_id}`} onClick={() => { const co2 = cMap.current[p.company_id]; if (co2) { setSelectedCompany(co2); setSelectedCompanyIndex(filteredCompanies.indexOf(co2)); } setSelectedPerson(p); setSelectedPersonIndex(filteredPeople.indexOf(p)); setSelectedRole(null); setSelectedRoleIndex(-1); }} style={{ borderBottom:"1px solid #F7F7F8", cursor:"pointer" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                            <div style={{ width:28, height:28, borderRadius:6, background: p.is_decision_maker ? "#1A1A1A" : "#EBEBED", display:"flex", alignItems:"center", justifyContent:"center", fontSize:12, fontWeight:700, color: p.is_decision_maker ? "#fff" : "#6B6F76", flexShrink:0 }}>
                              {p.name?.charAt(0) || "?"}
                            </div>
                            <span style={{ fontWeight:600, fontSize:13 }}>{p.name || "—"}</span>
                          </div>
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{p.role_at_company || p.title || "—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          <span style={{ fontWeight:500, fontSize:12 }}>{co?.name || "—"}</span>
                        </td>
                        <td style={{ padding:"9px 14px" }}>
                          {p.email ? <a href={`mailto:${p.email}`} onClick={e=>e.stopPropagation()} style={{ fontSize:12, color:"#5B5FC7", textDecoration:"none" }}>{p.email}</a> : <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{p.phone || "—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          {p.linkedin_url ? <a href={p.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{ padding:"3px 8px", borderRadius:4, background:"#0A66C2", color:"#fff", fontSize:10, fontWeight:600, textDecoration:"none" }}>LinkedIn</a> : <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>}
                        </td>
                        <td style={{ padding:"9px 14px" }}><SourcePill source={p.source} /></td>
                        <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                          {p.created_at ? new Date(p.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          ) : tab === "companies" ? (
            filteredCompanies.length === 0 ? (
              <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                <div style={{ fontSize:26, marginBottom:6 }}>∅</div>
                <div style={{ fontSize:14, fontWeight:500 }}>No companies yet</div>
                <div style={{ fontSize:12, marginTop:4 }}>Run the scraper to populate records.</div>
              </div>
            ) : (
              <table style={{ width:"100%", borderCollapse:"collapse" }}>
                <thead>
                  <tr>
                    <ColHead sk="name" sort={sort} onSort={doSort}>Company</ColHead>
                    <ColHead width={100}>Status</ColHead>
                    <ColHead width={150} sk="industry" sort={sort} onSort={doSort}>Industry</ColHead>
                    <ColHead width={90}>Fit</ColHead>
                    <ColHead width={90} sk="headcount" sort={sort} onSort={doSort}>Headcount</ColHead>
                    <ColHead width={90} sk="created_at" sort={sort} onSort={doSort}>Added</ColHead>
                  </tr>
                </thead>
                <tbody>
                  {filteredCompanies.slice(0,200).map(c => {
                    const st = STATUS[c.status] || { label:c.status||"—", bg:"#F2F3F5", color:"#6B6F76" };
                    const fitColors = { high:{bg:"#D1FAE5",color:"#065F46"}, medium:{bg:"#FFF0E1",color:"#AD5700"}, low:{bg:"#FDECEC",color:"#C13030"} };
                    const fit = fitColors[c.arteq_fit] || null;
                    return (
                      <tr key={c.id} onClick={() => { setSelectedCompany(c); setSelectedCompanyIndex(filteredCompanies.indexOf(c)); }} style={{ borderBottom:"1px solid #F7F7F8", cursor:"pointer" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:600, fontSize:13 }}>{c.name}</div>
                        </td>
                        <td style={{ padding:"9px 14px" }}>
                          <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:st.bg, color:st.color }}>{st.label}</span>
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{c.industry||"—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          {fit ? <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:fit.bg, color:fit.color }}>{c.arteq_fit}</span>
                            : <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{c.headcount||"—"}</td>
                        <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                          {c.created_at ? new Date(c.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
          ) : tab === "matches" ? (
            (() => {
              const rMap = {}; roles.forEach(r => { rMap[r.id] = r; });
              const filteredMatches = allMatches.filter(m => {
                if (matchStatusFilter !== "all" && m.status !== matchStatusFilter) return false;
                if (search) {
                  const cand = allCandidates[m.candidate_id];
                  const role = rMap[m.role_id];
                  const co = role ? cMap.current[role.company_id] : null;
                  const hay = `${cand?.full_name||""} ${role?.title||""} ${co?.name||""}`.toLowerCase();
                  if (!hay.includes(search.toLowerCase())) return false;
                }
                return true;
              });
              return filteredMatches.length === 0 ? (
                <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                  <div style={{ fontSize:26, marginBottom:6 }}>◇</div>
                  <div style={{ fontSize:14, fontWeight:500 }}>No matches yet</div>
                  <div style={{ fontSize:12, marginTop:4 }}>Run the research agent to generate candidate matches.</div>
                </div>
              ) : (
                <table style={{ width:"100%", borderCollapse:"collapse" }}>
                  <thead>
                    <tr>
                      <ColHead width={180}>Role</ColHead>
                      <ColHead width={170}>Candidate</ColHead>
                      <ColHead width={70} align="center">Score</ColHead>
                      <ColHead width={90}>Status</ColHead>
                      <ColHead width={80}>Function</ColHead>
                      <ColHead width={80}>Location</ColHead>
                      <ColHead width={90}>Created</ColHead>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMatches.slice(0,200).map(match => {
                      const cand = allCandidates[match.candidate_id] || {};
                      const role = rMap[match.role_id] || {};
                      const co = cMap.current[role.company_id] || {};
                      return (
                        <tr key={match.id} onClick={() => {
                          if (co.id) { setSelectedCompany(co); setSelectedCompanyIndex(-1); }
                          if (role.id) { setSelectedRole(role); setSelectedRoleIndex(-1); }
                          setSelectedPerson(null); setSelectedPersonIndex(-1);
                        }} style={{ cursor:"pointer", borderBottom:"1px solid #F7F7F8" }}
                          onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                          onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                          <td style={{ padding:"9px 14px" }}>
                            <div style={{ fontWeight:600, fontSize:12 }}>{cleanTitle(role.title) || "—"}</div>
                            <div style={{ fontSize:10, color:"#A0A3A9" }}>{co.name || "—"}</div>
                          </td>
                          <td style={{ padding:"9px 14px" }}>
                            <div style={{ fontWeight:600, fontSize:12 }}>{cand.full_name || "—"}</div>
                            <div style={{ fontSize:10, color:"#A0A3A9" }}>{cand.current_title || "—"}</div>
                          </td>
                          <td style={{ padding:"9px 14px", textAlign:"center" }}><MatchScorePill score={match.match_score} /></td>
                          <td style={{ padding:"9px 14px" }}><MatchStatusPill status={match.status} /></td>
                          <td style={{ padding:"9px 14px" }}>
                            {match.function_match ? <span style={{ fontSize:11, color:"#065F46" }}>✓</span> : <span style={{ fontSize:11, color:"#A0A3A9" }}>✗</span>}
                          </td>
                          <td style={{ padding:"9px 14px" }}>
                            {match.location_match ? <span style={{ fontSize:11, color:"#065F46" }}>✓</span> : <span style={{ fontSize:11, color:"#A0A3A9" }}>✗</span>}
                          </td>
                          <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                            {match.created_at ? new Date(match.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              );
            })()
          ) : (
            /* Agent Log Tab */
            agentLogs.length === 0 ? (
              <div style={{ padding:60, textAlign:"center", color:"#A0A3A9" }}>
                <div style={{ fontSize:26, marginBottom:6 }}>🤖</div>
                <div style={{ fontSize:14, fontWeight:500 }}>No agent activity yet</div>
                <div style={{ fontSize:12, marginTop:4 }}>Run the orchestrator to generate decisions.</div>
              </div>
            ) : (
              <div style={{ padding:"16px 20px" }}>
                {(() => {
                  const ACTION_STYLE = {
                    promote_company:   { icon:"⬆", bg:"#D1FAE5", color:"#065F46", label:"Promoted" },
                    downgrade_company: { icon:"⬇", bg:"#FDECEC", color:"#C13030", label:"Downgraded" },
                    expire_role:       { icon:"⏰", bg:"#FFF0E1", color:"#AD5700", label:"Expired" },
                    dedup_contact:     { icon:"🔗", bg:"#DBEAFE", color:"#1D4ED8", label:"Deduped" },
                    enrich_contact:    { icon:"✉", bg:"#EDE9FE", color:"#6D28D9", label:"Enriched" },
                    outreach_draft:    { icon:"📝", bg:"#DBEAFE", color:"#1D4ED8", label:"Draft" },
                    outreach_sent:     { icon:"📨", bg:"#D1FAE5", color:"#065F46", label:"Sent" },
                    outreach_reply:    { icon:"💬", bg:"#D1FAE5", color:"#065F46", label:"Auto-Reply" },
                    inbound_reply:     { icon:"📩", bg:"#FEF3C7", color:"#92400E", label:"Reply Received" },
                    sdr_handoff_ae:    { icon:"🤝", bg:"#EDE9FE", color:"#6D28D9", label:"SDR → AE" },
                    ae_response:       { icon:"🎯", bg:"#D1FAE5", color:"#065F46", label:"AE Response" },
                    ae_meeting_prep:   { icon:"📋", bg:"#FEF3C7", color:"#92400E", label:"Meeting Prep" },
                    ae_proposal:       { icon:"📄", bg:"#EDE9FE", color:"#6D28D9", label:"Proposal" },
                  };
                  // Group by date
                  const groups = {};
                  agentLogs.forEach(log => {
                    const d = log.created_at ? new Date(log.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : "Unknown";
                    if (!groups[d]) groups[d] = [];
                    groups[d].push(log);
                  });
                  return Object.entries(groups).map(([date, logs]) => (
                    <div key={date} style={{ marginBottom:20 }}>
                      <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:8, borderBottom:"1px solid #F7F7F8", paddingBottom:6 }}>{date}</div>
                      {logs.map((log, i) => {
                        const st = ACTION_STYLE[log.action] || { icon:"●", bg:"#F2F3F5", color:"#6B6F76", label:log.action };
                        return (
                          <div key={log.id || i} style={{ display:"flex", gap:10, padding:"8px 0", borderBottom:"1px solid #F7F7F8" }}>
                            <span style={{ width:28, height:28, borderRadius:6, background:st.bg, color:st.color, display:"flex", alignItems:"center", justifyContent:"center", fontSize:14, flexShrink:0 }}>{st.icon}</span>
                            <div style={{ flex:1, minWidth:0 }}>
                              <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                                <span style={{ padding:"2px 6px", borderRadius:3, fontSize:10, fontWeight:600, background:st.bg, color:st.color }}>{st.label}</span>
                                <span style={{ fontSize:11, color:"#A0A3A9" }}>{log.entity_type}</span>
                                <span style={{ fontSize:10, color:"#A0A3A9", marginLeft:"auto" }}>
                                  {log.created_at ? new Date(log.created_at).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"}) : ""}
                                </span>
                              </div>
                              <div style={{ fontSize:12, color:"#1A1A1A", marginTop:3, lineHeight:1.4 }}>{log.reason || "—"}</div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ));
                })()}
              </div>
            )
          )}
        </div>
        </>
        )}
      </div>

    </div>
  );
}
