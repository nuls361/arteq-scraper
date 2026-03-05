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
  const active = sort?.key === sk;
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
        {active && <span style={{ fontSize:9 }}>{sort.dir==="asc"?"▲":"▼"}</span>}
      </span>
    </th>
  );
}

function DetailDrawer({ role, company, dm, allDms = [], onClose }) {
  if (!role) return null;
  const fields = [
    ["Score", role.final_score ?? role.rule_score ?? "—"],
    ["AI Score", role.ai_score ?? "—"],
    ["Location", role.location || "—"],
    ["Remote", role.is_remote ? "Yes" : "No"],
    ["Posted", role.posted_at ? new Date(role.posted_at).toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric"}) : "—"],
    ["Status", role.status || "—"],
    ["DM Guess", role.decision_maker_guess || "—"],
    ["Company Stage", role.company_stage_guess || "—"],
  ];

  return (
    <>
      <div onClick={onClose} style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.06)", zIndex:90 }} />
      <div style={{
        position:"fixed", top:0, right:0, bottom:0, width:400,
        background:"#fff", borderLeft:"1px solid #EBEBED",
        boxShadow:"-8px 0 30px rgba(0,0,0,0.06)", zIndex:100,
        display:"flex", flexDirection:"column",
        fontFamily:"'Inter',-apple-system,sans-serif",
        animation:"slideIn .15s ease-out",
      }}>
        <style>{`@keyframes slideIn{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>

        <div style={{ padding:"20px 24px", borderBottom:"1px solid #EBEBED", display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
          <div>
            <div style={{ fontSize:11, color:"#A0A3A9", marginBottom:4 }}>{company?.name || "Unknown"}</div>
            <div style={{ fontSize:17, fontWeight:600, color:"#1A1A1A", lineHeight:1.3 }}>{role.title}</div>
            <div style={{ display:"flex", gap:6, marginTop:10, flexWrap:"wrap" }}>
              <TierPill tier={role.tier} />
              <EngPill type={role.engagement_type} />
              <SourcePill source={role.source} />
            </div>
          </div>
          <button onClick={onClose} style={{
            width:28, height:28, borderRadius:6, border:"1px solid #EBEBED",
            background:"#fff", cursor:"pointer", fontSize:15, color:"#6B6F76",
            display:"flex", alignItems:"center", justifyContent:"center",
          }}>×</button>
        </div>

        <div style={{ flex:1, overflow:"auto", padding:"16px 24px" }}>
          {fields.map(([k,v]) => (
            <div key={k} style={{ display:"flex", padding:"9px 0", borderBottom:"1px solid #F7F7F8" }}>
              <span style={{ width:130, fontSize:12, color:"#A0A3A9", flexShrink:0 }}>{k}</span>
              <span style={{ fontSize:13, color:"#1A1A1A", fontWeight:500 }}>{String(v)}</span>
            </div>
          ))}

          {/* Contacts */}
          {(allDms.length > 0 || dm) && (
            <div style={{ marginTop:16 }}>
              <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:8 }}>Contacts ({allDms.length || 1})</div>
              {(allDms.length > 0 ? allDms : [dm]).filter(Boolean).map((person, idx) => (
                <div key={person.id || idx} style={{ background:"#F7F7F8", borderRadius:8, padding:"12px 14px", marginBottom:6 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                    <div style={{ width:32, height:32, borderRadius:7, background: person.is_decision_maker || idx === 0 ? "#1A1A1A" : "#EBEBED", display:"flex", alignItems:"center", justifyContent:"center", fontSize:13, fontWeight:700, color: person.is_decision_maker || idx === 0 ? "#fff" : "#6B6F76" }}>
                      {person.name?.charAt(0) || "?"}
                    </div>
                    <div style={{ flex:1 }}>
                      <div style={{ display:"flex", alignItems:"center", gap:5 }}>
                        <span style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>{person.name}</span>
                        {(person.is_decision_maker || idx === 0) && <span style={{ fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3, background:"#FDECEC", color:"#C13030" }}>DM</span>}
                      </div>
                      <div style={{ fontSize:11, color:"#6B6F76" }}>{person.role_at_company || person.title}</div>
                    </div>
                    {person.linkedin_url && (
                      <a href={person.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{
                        padding:"4px 8px", borderRadius:5, background:"#0A66C2", color:"#fff",
                        fontSize:10, fontWeight:600, textDecoration:"none", whiteSpace:"nowrap",
                      }}>LinkedIn ↗</a>
                    )}
                  </div>
                  {(person.email || person.phone) && (
                    <div style={{ marginTop:8, display:"flex", gap:6, flexWrap:"wrap" }}>
                      {person.email && (
                        <a href={`mailto:${person.email}`} style={{ display:"inline-flex", alignItems:"center", gap:3, padding:"3px 8px", borderRadius:4, background:"#fff", border:"1px solid #EBEBED", fontSize:11, color:"#1A1A1A", textDecoration:"none", fontWeight:500 }}>
                          ✉ {person.email}
                        </a>
                      )}
                      {person.phone && (
                        <span style={{ display:"inline-flex", alignItems:"center", gap:3, padding:"3px 8px", borderRadius:4, background:"#fff", border:"1px solid #EBEBED", fontSize:11, color:"#1A1A1A", fontWeight:500 }}>
                          ☎ {person.phone}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {role.requirements_summary && (
            <div style={{ marginTop:18 }}>
              <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:6 }}>Requirements</div>
              <div style={{ fontSize:13, color:"#6B6F76", lineHeight:1.6, background:"#F7F7F8", padding:"10px 12px", borderRadius:6 }}>{role.requirements_summary}</div>
            </div>
          )}

          {role.engagement_reasoning && (
            <div style={{ marginTop:14 }}>
              <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:6 }}>Reasoning</div>
              <div style={{ fontSize:13, color:"#6B6F76", lineHeight:1.6, background:"#F7F7F8", padding:"10px 12px", borderRadius:6 }}>{role.engagement_reasoning}</div>
            </div>
          )}

          {role.outreach_angle && (
            <div style={{ marginTop:14 }}>
              <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:6 }}>Outreach angle</div>
              <div style={{ fontSize:13, color:"#6B6F76", lineHeight:1.6, background:"#F7F7F8", padding:"10px 12px", borderRadius:6 }}>{role.outreach_angle}</div>
            </div>
          )}

          {role.signals && role.signals.length > 0 && (
            <div style={{ marginTop:14 }}>
              <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:6 }}>Signals</div>
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
        </div>
      </div>
    </>
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

const ENTRY_TYPE = {
  signal:       { label: "Signal",       icon: "⚡", bg: "#FDECEC", color: "#C13030" },
  news:         { label: "News",         icon: "📰", bg: "#DBEAFE", color: "#1D4ED8" },
  meeting_note: { label: "Meeting Note", icon: "🤝", bg: "#EDE9FE", color: "#6D28D9" },
  note:         { label: "Note",         icon: "📝", bg: "#FFF0E1", color: "#AD5700" },
  file:         { label: "File",         icon: "📎", bg: "#F0FDF4", color: "#15803D" },
  agent_action: { label: "Agent",        icon: "🤖", bg: "#EDE9FE", color: "#6D28D9" },
  outreach:     { label: "Outreach",     icon: "📨", bg: "#DBEAFE", color: "#1D4ED8" },
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
                {isOutbound ? "Niels (Arteq)" : contactName}
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
                {date ? date.toLocaleDateString("de-DE", { day:"numeric", month:"short", hour:"2-digit", minute:"2-digit" }) : ""}
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

function CompanyDossier({ company, contacts = [], onClose, onContactsChanged }) {
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

  const loadEntries = useCallback(async () => {
    if (!company) return;
    setLoading(true);
    try {
      const data = await supaFetch(
        "company_dossier",
        `company_id=eq.${company.id}&order=created_at.desc&limit=200`
      );
      setEntries(data || []);
    } catch (e) {
      console.error("Dossier load error:", e);
    }
    setLoading(false);
  }, [company]);

  useEffect(() => { loadEntries(); }, [loadEntries]);

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
        author: "Arteq Team",
      });
      setNoteTitle("");
      setNoteContent("");
      await loadEntries();
    } catch (e) {
      console.error("Save note error:", e);
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
        author: "Arteq Team",
      });
      setNoteContent("");
      await loadEntries();
    } catch (err) {
      console.error("File upload error:", err);
      alert("Upload fehlgeschlagen: " + err.message);
    }
    setUploading(false);
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleAddContact = async () => {
    if (!newContact.name.trim()) return;
    setSavingContact(true);
    try {
      const contactRes = await supaPost("contact", {
        name: newContact.name.trim(),
        title: newContact.title.trim() || null,
        linkedin_url: newContact.linkedin_url.trim() || null,
        email: newContact.email.trim() || null,
        phone: newContact.phone.trim() || null,
        source: "manual",
      });
      if (contactRes && contactRes[0]) {
        await supaPost("company_contact", {
          company_id: company.id,
          contact_id: contactRes[0].id,
          role_at_company: newContact.title.trim() || "",
          is_decision_maker: contacts.length === 0,
        });
      }
      setNewContact({ name: "", title: "", linkedin_url: "", email: "", phone: "" });
      setShowAddContact(false);
      if (onContactsChanged) onContactsChanged();
    } catch (e) {
      console.error("Add contact error:", e);
      alert("Contact konnte nicht gespeichert werden: " + e.message);
    }
    setSavingContact(false);
  };

  if (!company) return null;

  const st = { lead:{bg:"#EDE9FE",color:"#6D28D9"}, prospect:{bg:"#DBEAFE",color:"#1D4ED8"}, active:{bg:"#D1FAE5",color:"#065F46"}, client:{bg:"#D1FAE5",color:"#047857"}, churned:{bg:"#FDECEC",color:"#C13030"} };
  const statusStyle = st[company.status] || { bg:"#F2F3F5", color:"#6B6F76" };
  const fitColors = { high:{bg:"#D1FAE5",color:"#065F46"}, medium:{bg:"#FFF0E1",color:"#AD5700"}, low:{bg:"#FDECEC",color:"#C13030"} };

  return (
    <>
      <div onClick={onClose} style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.06)", zIndex:90 }} />
      <div style={{
        position:"fixed", top:0, right:0, bottom:0, width:520,
        background:"#fff", borderLeft:"1px solid #EBEBED",
        boxShadow:"-8px 0 30px rgba(0,0,0,0.06)", zIndex:100,
        display:"flex", flexDirection:"column",
        fontFamily:"'Inter',-apple-system,sans-serif",
        animation:"slideIn .15s ease-out",
      }}>
        <style>{`@keyframes slideIn{from{transform:translateX(100%)}to{transform:translateX(0)}}`}</style>

        {/* Header */}
        <div style={{ padding:"20px 24px", borderBottom:"1px solid #EBEBED" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
            <div>
              <div style={{ fontSize:18, fontWeight:700, color:"#1A1A1A", lineHeight:1.3 }}>{company.name}</div>
              {company.domain && <div style={{ fontSize:12, color:"#5B5FC7", marginTop:2 }}>{company.domain}</div>}
              <div style={{ display:"flex", gap:6, marginTop:10, flexWrap:"wrap" }}>
                <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:statusStyle.bg, color:statusStyle.color }}>{company.status || "—"}</span>
                {company.arteq_fit && fitColors[company.arteq_fit] && (
                  <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:fitColors[company.arteq_fit].bg, color:fitColors[company.arteq_fit].color }}>Fit: {company.arteq_fit}</span>
                )}
                {company.industry && <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:"#F2F3F5", color:"#6B6F76" }}>{company.industry}</span>}
                {company.funding_stage && company.funding_stage !== "unknown" && (
                  <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:"#F2F3F5", color:"#6B6F76" }}>{company.funding_stage}</span>
                )}
                {company.pipeline_stage && company.pipeline_stage !== "prospect" && (
                  <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:600,
                    background: {"sdr_outreach":"#DBEAFE","sdr_followup":"#DBEAFE","qualified":"#D1FAE5","meeting_prep":"#FEF3C7","meeting_done":"#FEF3C7","proposal":"#EDE9FE","closed_won":"#D1FAE5","closed_lost":"#FDECEC","nurture":"#F2F3F5"}[company.pipeline_stage] || "#F2F3F5",
                    color: {"sdr_outreach":"#1D4ED8","sdr_followup":"#1D4ED8","qualified":"#065F46","meeting_prep":"#92400E","meeting_done":"#92400E","proposal":"#6D28D9","closed_won":"#065F46","closed_lost":"#C13030","nurture":"#6B6F76"}[company.pipeline_stage] || "#6B6F76",
                  }}>{company.pipeline_stage.replace(/_/g, " ")}</span>
                )}
                {company.agent_owner && company.agent_owner !== "sdr" && (
                  <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:600, background:"#EDE9FE", color:"#6D28D9" }}>
                    {company.agent_owner === "ae" ? "AE" : company.agent_owner}
                  </span>
                )}
              </div>
            </div>
            <button onClick={onClose} style={{
              width:28, height:28, borderRadius:6, border:"1px solid #EBEBED",
              background:"#fff", cursor:"pointer", fontSize:15, color:"#6B6F76",
              display:"flex", alignItems:"center", justifyContent:"center",
            }}>×</button>
          </div>

          {/* Quick stats */}
          <div style={{ display:"flex", gap:16, marginTop:14 }}>
            {[
              ["Headcount", company.headcount || "—"],
              ["Founded", company.founded_year || "—"],
              ["HQ", company.hq_city || "—"],
            ].map(([k,v]) => (
              <div key={k}>
                <div style={{ fontSize:10, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4 }}>{k}</div>
                <div style={{ fontSize:13, fontWeight:600, color:"#1A1A1A", marginTop:1 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Contacts Section ── */}
        <div style={{ padding:"14px 24px", borderBottom:"1px solid #EBEBED" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10 }}>
            <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8 }}>
              Contacts ({contacts.length})
            </div>
            <button onClick={() => setShowAddContact(!showAddContact)} style={{
              padding:"3px 10px", borderRadius:5, fontSize:11, fontWeight:600, cursor:"pointer",
              border:"1px solid #EBEBED", background: showAddContact ? "#1A1A1A" : "#fff",
              color: showAddContact ? "#fff" : "#6B6F76", fontFamily:"inherit",
            }}>{showAddContact ? "Cancel" : "+ Add"}</button>
          </div>

          {showAddContact && (
            <div style={{ background:"#FAFAFA", borderRadius:8, padding:12, marginBottom:10, border:"1px solid #EBEBED" }}>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6 }}>
                <input value={newContact.name} onChange={e => setNewContact(p => ({...p, name: e.target.value}))} placeholder="Name *" style={{ padding:"6px 8px", borderRadius:5, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none", gridColumn: "1 / -1" }} />
                <input value={newContact.title} onChange={e => setNewContact(p => ({...p, title: e.target.value}))} placeholder="Titel (z.B. CEO)" style={{ padding:"6px 8px", borderRadius:5, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                <input value={newContact.linkedin_url} onChange={e => setNewContact(p => ({...p, linkedin_url: e.target.value}))} placeholder="LinkedIn URL" style={{ padding:"6px 8px", borderRadius:5, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                <input value={newContact.email} onChange={e => setNewContact(p => ({...p, email: e.target.value}))} placeholder="Email" style={{ padding:"6px 8px", borderRadius:5, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
                <input value={newContact.phone} onChange={e => setNewContact(p => ({...p, phone: e.target.value}))} placeholder="Telefon" style={{ padding:"6px 8px", borderRadius:5, border:"1px solid #EBEBED", fontSize:12, fontFamily:"inherit", outline:"none" }} />
              </div>
              <button onClick={handleAddContact} disabled={savingContact || !newContact.name.trim()} style={{
                marginTop:8, padding:"5px 14px", borderRadius:5, border:"none", fontSize:12, fontWeight:600, cursor: newContact.name.trim() ? "pointer" : "default", fontFamily:"inherit",
                background: newContact.name.trim() ? "#1A1A1A" : "#EBEBED", color: newContact.name.trim() ? "#fff" : "#A0A3A9",
              }}>{savingContact ? "Saving..." : "Save Contact"}</button>
            </div>
          )}

          {contacts.length === 0 && !showAddContact ? (
            <div style={{ padding:"12px 0", textAlign:"center", color:"#A0A3A9", fontSize:12 }}>No contacts yet. Click "+ Add" to add one.</div>
          ) : (
            <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
              {contacts.map((c, i) => (
                <div key={c.id || i} style={{ display:"flex", alignItems:"center", gap:10, padding:"8px 10px", background:"#F7F7F8", borderRadius:8 }}>
                  <div style={{ width:32, height:32, borderRadius:7, background: c.is_decision_maker ? "#1A1A1A" : "#EBEBED", display:"flex", alignItems:"center", justifyContent:"center", fontSize:13, fontWeight:700, color: c.is_decision_maker ? "#fff" : "#6B6F76", flexShrink:0 }}>
                    {c.name?.charAt(0) || "?"}
                  </div>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                      <span style={{ fontSize:13, fontWeight:600, color:"#1A1A1A" }}>{c.name}</span>
                      {c.is_decision_maker && <span style={{ fontSize:9, fontWeight:700, padding:"1px 5px", borderRadius:3, background:"#FDECEC", color:"#C13030" }}>DM</span>}
                    </div>
                    <div style={{ fontSize:11, color:"#6B6F76" }}>{c.role_at_company || c.title || ""}</div>
                    <div style={{ display:"flex", gap:6, marginTop:3, flexWrap:"wrap" }}>
                      {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{ fontSize:10, color:"#0A66C2", textDecoration:"none", fontWeight:600 }}>LinkedIn</a>}
                      {c.email && <a href={`mailto:${c.email}`} style={{ fontSize:10, color:"#5B5FC7", textDecoration:"none" }}>{c.email}</a>}
                      {c.phone && <span style={{ fontSize:10, color:"#6B6F76" }}>{c.phone}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Add Note Form */}
        <div style={{ padding:"14px 24px", borderBottom:"1px solid #EBEBED", background:"#FAFAFA" }}>
          <div style={{ display:"flex", gap:6, marginBottom:8 }}>
            {["meeting_note", "note"].map(t => {
              const et = ENTRY_TYPE[t];
              const active = noteType === t;
              return (
                <button key={t} onClick={() => setNoteType(t)} style={{
                  padding:"4px 10px", borderRadius:4, fontSize:12, fontWeight:500, cursor:"pointer",
                  border: active ? "1.5px solid #1A1A1A" : "1px solid #EBEBED",
                  background: active ? "#1A1A1A" : "#fff",
                  color: active ? "#fff" : "#6B6F76",
                  fontFamily:"inherit",
                }}>{et.icon} {et.label}</button>
              );
            })}
          </div>
          <input
            value={noteTitle}
            onChange={e => setNoteTitle(e.target.value)}
            placeholder="Title (optional)"
            style={{
              width:"100%", padding:"7px 10px", borderRadius:6, border:"1px solid #EBEBED",
              fontSize:12, fontFamily:"inherit", outline:"none", color:"#1A1A1A",
              marginBottom:6, boxSizing:"border-box",
            }}
          />
          <textarea
            value={noteContent}
            onChange={e => setNoteContent(e.target.value)}
            placeholder={noteType === "meeting_note" ? "Meeting notes — what was discussed, action items, key takeaways…" : "General note about this company…"}
            rows={3}
            style={{
              width:"100%", padding:"7px 10px", borderRadius:6, border:"1px solid #EBEBED",
              fontSize:12, fontFamily:"inherit", outline:"none", color:"#1A1A1A",
              resize:"vertical", lineHeight:1.5, boxSizing:"border-box",
            }}
          />
          <button
            onClick={handleAddNote}
            disabled={saving || !noteContent.trim()}
            style={{
              marginTop:6, padding:"6px 16px", borderRadius:6,
              background: noteContent.trim() ? "#1A1A1A" : "#EBEBED",
              color: noteContent.trim() ? "#fff" : "#A0A3A9",
              border:"none", fontSize:12, fontWeight:600, cursor: noteContent.trim() ? "pointer" : "default",
              fontFamily:"inherit",
            }}
          >{saving ? "Saving…" : "Add to Dossier"}</button>

            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileUpload}
              style={{ display: "none" }}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.png,.jpg,.jpeg,.gif,.svg,.zip"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              style={{
                marginTop:6, marginLeft:8, padding:"6px 16px", borderRadius:6,
                background:"#fff", color:"#6B6F76",
                border:"1px solid #EBEBED", fontSize:12, fontWeight:600,
                cursor: uploading ? "default" : "pointer",
                fontFamily:"inherit",
              }}
            >{uploading ? "Uploading…" : "📎 Upload File"}</button>
        </div>

        {/* Outreach Conversations */}
        {outreachThreads.length > 0 && (
          <div style={{ padding:"0 24px" }}>
            <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"14px 0 8px" }}>
              Outreach Conversations ({outreachThreads.length})
            </div>
            {outreachThreads.map((thread, i) => (
              <OutreachThread key={thread[0]?.thread_id || i} thread={thread} contacts={threadContacts} />
            ))}
          </div>
        )}

        {/* Dossier Feed */}
        <div style={{ flex:1, overflow:"auto", padding:"0 24px 24px" }}>
          <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"14px 0 8px" }}>
            Intelligence Feed ({entries.length})
          </div>

          {loading ? (
            <div style={{ padding:40, textAlign:"center", color:"#A0A3A9", fontSize:13 }}>Loading dossier…</div>
          ) : entries.length === 0 ? (
            <div style={{ padding:40, textAlign:"center", color:"#A0A3A9" }}>
              <div style={{ fontSize:22, marginBottom:6 }}>📋</div>
              <div style={{ fontSize:13, fontWeight:500 }}>No entries yet</div>
              <div style={{ fontSize:12, marginTop:4 }}>Signals will appear here automatically. Add meeting notes above.</div>
            </div>
          ) : (
            <div style={{ position:"relative" }}>
              {/* Timeline line */}
              <div style={{ position:"absolute", left:11, top:8, bottom:8, width:2, background:"#EBEBED" }} />

              {entries.map((entry, i) => {
                const et = ENTRY_TYPE[entry.entry_type] || ENTRY_TYPE.note;
                const date = entry.created_at ? new Date(entry.created_at) : null;
                return (
                  <div key={entry.id || i} style={{ position:"relative", paddingLeft:32, paddingBottom:16 }}>
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
                          {date ? date.toLocaleDateString("de-DE", { day:"numeric", month:"short", year:"numeric" }) : "—"}
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
                        <div style={{ fontSize:12, color:"#6B6F76", lineHeight:1.6, whiteSpace:"pre-wrap" }}>
                          {entry.content}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function ArteqCRM() {
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
  const [agentLogs, setAgentLogs] = useState([]);
  const cMap = useRef({});

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [c, r, cc, logs] = await Promise.all([
        supaFetch("company","select=*&limit=1000"),
        supaFetch("role","select=*&limit=1000"),
        supaFetch("company_contact","select=*,contact:contact_id(*)&limit=2000").catch(() => []),
        supaFetch("agent_log","select=*&order=created_at.desc&limit=200").catch(() => []),
      ]);
      setAgentLogs(logs || []);
      setCompanies(c);
      const m = {}; c.forEach(co => { m[co.id] = co; }); cMap.current = m;
      setRoles(r);
      // Build company_id → contact maps (primary + all)
      const dmMap = {};
      const allMap = {};
      (cc || []).forEach(link => {
        if (link.contact) {
          // Primary DM = first is_decision_maker=true found
          if (link.is_decision_maker && !dmMap[link.company_id]) {
            dmMap[link.company_id] = link.contact;
          }
          // All contacts per company
          if (!allMap[link.company_id]) allMap[link.company_id] = [];
          allMap[link.company_id].push({ ...link.contact, role_at_company: link.role_at_company, is_decision_maker: link.is_decision_maker });
        }
      });
      setContacts(dmMap);
      setAllContacts(allMap);
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

  return (
    <div style={{ display:"flex", height:"100vh", fontFamily:"'Inter',-apple-system,BlinkMacSystemFont,sans-serif", background:"#fff", color:"#1A1A1A", fontSize:13 }}>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />

      {/* ── Sidebar ── */}
      <div style={{ width:210, borderRight:"1px solid #EBEBED", padding:"16px 10px", display:"flex", flexDirection:"column", background:"#FAFAFA", flexShrink:0 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8, padding:"4px 10px", marginBottom:28 }}>
          <div style={{ width:24, height:24, borderRadius:6, background:"#1A1A1A", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff", fontWeight:800, fontSize:12 }}>A</div>
          <span style={{ fontWeight:700, fontSize:15, letterSpacing:-0.5 }}>Arteq</span>
        </div>

        <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"0 10px", marginBottom:8 }}>Pipeline</div>

        {[
          { icon:"⊙", label:"Roles", count:roles.length, key:"roles" },
          { icon:"○", label:"Companies", count:companies.length, key:"companies" },
          { icon:"◎", label:"Agent Log", count:null, key:"agent" },
        ].map(n => (
          <div key={n.label} onClick={() => { setTab(n.key); setSearch(""); setTierFilter("all"); setSourceFilter("all"); setStatusFilter("all"); }} style={{
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
        <div style={{ fontSize:10, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.8, padding:"0 10px", marginBottom:8 }}>Views</div>

        {[
          { icon:"●", label:"Hot leads", count:tierCounts.hot||0, color:"#E5484D", tier:"hot" },
          { icon:"●", label:"Warm leads", count:tierCounts.warm||0, color:"#F5A623", tier:"warm" },
          { icon:"●", label:"Parked", count:tierCounts.parked||0, color:"#A0A3A9", tier:"parked" },
        ].map(n => (
          <div key={n.label} onClick={() => { setTab("roles"); setTierFilter(tierFilter===n.tier?"all":n.tier); }} style={{
            display:"flex", alignItems:"center", gap:8, padding:"7px 10px", borderRadius:6,
            background: tierFilter===n.tier?"#EBEBED":"transparent",
            color:tierFilter===n.tier?"#1A1A1A":"#6B6F76",
            fontSize:13, fontWeight:tierFilter===n.tier?600:400, cursor:"pointer", marginBottom:1,
          }}>
            <span style={{ fontSize:8, color:n.color }}>●</span>
            <span style={{ flex:1 }}>{n.label}</span>
            <span style={{ fontSize:11, color:"#A0A3A9" }}>{n.count}</span>
          </div>
        ))}

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

        {/* Topbar */}
        <div style={{ padding:"12px 20px", borderBottom:"1px solid #EBEBED", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontSize:15, fontWeight:600 }}>{tab === "roles" ? "Roles" : tab === "companies" ? "Companies" : "Agent Log"}</span>
            <span style={{ fontSize:12, color:"#A0A3A9" }}>{tab === "roles" ? `${filtered.length} records` : tab === "companies" ? `${filteredCompanies.length} records` : `${agentLogs.length} decisions`}</span>
          </div>
          <button onClick={load} style={{
            padding:"5px 12px", borderRadius:6, border:"1px solid #EBEBED",
            background:"#fff", cursor:"pointer", fontSize:12, fontWeight:500,
            color:"#6B6F76", fontFamily:"inherit",
          }}>↻ Refresh</button>
        </div>

        {/* Filters */}
        {tab === "agent" ? null : tab === "roles" ? (
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
                      <tr key={r.id} onClick={()=>setSelected(r)} style={{ cursor:"pointer", borderBottom:"1px solid #F7F7F8" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}><TierPill tier={r.tier} /></td>
                        <td style={{ padding:"9px 14px", textAlign:"center" }}><Score v={r.final_score??r.rule_score} /></td>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:600, fontSize:13 }}>{co?.name||"—"}</div>
                          {co?.is_agency && <span style={{ fontSize:10, color:"#E5484D", fontWeight:500 }}>Agency</span>}
                        </td>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:500 }}>{r.title}</div>
                          {r.requirements_summary && <div style={{ fontSize:11, color:"#A0A3A9", lineHeight:1.3, maxWidth:300, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.requirements_summary}</div>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{r.location||"—"}</td>
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
                    <ColHead width={120} sk="funding_stage" sort={sort} onSort={doSort}>Funding</ColHead>
                    <ColHead width={90} sk="headcount" sort={sort} onSort={doSort}>Headcount</ColHead>
                    <ColHead width={80}>Agency</ColHead>
                    <ColHead width={90} sk="created_at" sort={sort} onSort={doSort}>Added</ColHead>
                  </tr>
                </thead>
                <tbody>
                  {filteredCompanies.slice(0,200).map(c => {
                    const st = STATUS[c.status] || { label:c.status||"—", bg:"#F2F3F5", color:"#6B6F76" };
                    const fitColors = { high:{bg:"#D1FAE5",color:"#065F46"}, medium:{bg:"#FFF0E1",color:"#AD5700"}, low:{bg:"#FDECEC",color:"#C13030"} };
                    const fit = fitColors[c.arteq_fit] || null;
                    return (
                      <tr key={c.id} onClick={() => setSelectedCompany(c)} style={{ borderBottom:"1px solid #F7F7F8", cursor:"pointer" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F7F7F8"}
                        onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"9px 14px" }}>
                          <div style={{ fontWeight:600, fontSize:13 }}>{c.name}</div>
                          {c.website && <a href={c.website.startsWith("http")?c.website:`https://${c.website}`} target="_blank" rel="noopener" style={{ fontSize:11, color:"#5B5FC7", textDecoration:"none" }}>{c.domain || c.website}</a>}
                        </td>
                        <td style={{ padding:"9px 14px" }}>
                          <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:st.bg, color:st.color }}>{st.label}</span>
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{c.industry||"—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          {fit ? <span style={{ padding:"3px 8px", borderRadius:4, fontSize:12, fontWeight:500, background:fit.bg, color:fit.color }}>{c.arteq_fit}</span>
                            : <span style={{ color:"#A0A3A9", fontSize:12 }}>—</span>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>
                          {c.funding_stage && c.funding_stage !== "unknown" ? c.funding_stage : "—"}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#6B6F76", fontSize:12 }}>{c.headcount||"—"}</td>
                        <td style={{ padding:"9px 14px" }}>
                          {c.is_agency ? <span style={{ fontSize:11, fontWeight:600, color:"#E5484D" }}>⚠ Yes</span> : <span style={{ fontSize:11, color:"#30A46C" }}>✓ No</span>}
                        </td>
                        <td style={{ padding:"9px 14px", color:"#A0A3A9", fontSize:12, whiteSpace:"nowrap" }}>
                          {c.created_at ? new Date(c.created_at).toLocaleDateString("en-GB",{day:"numeric",month:"short"}) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )
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
                    const d = log.created_at ? new Date(log.created_at).toLocaleDateString("de-DE",{day:"numeric",month:"short",year:"numeric"}) : "Unknown";
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
                                  {log.created_at ? new Date(log.created_at).toLocaleTimeString("de-DE",{hour:"2-digit",minute:"2-digit"}) : ""}
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
      </div>

      {tab === "roles" && selected && <DetailDrawer role={selected} company={cMap.current[selected.company_id]} dm={contacts[selected.company_id]} allDms={allContacts[selected.company_id] || []} onClose={()=>setSelected(null)} />}
      {tab === "companies" && selectedCompany && <CompanyDossier company={selectedCompany} contacts={allContacts[selectedCompany.id] || []} onClose={() => setSelectedCompany(null)} onContactsChanged={load} />}
    </div>
  );
}
