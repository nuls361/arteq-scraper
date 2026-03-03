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

function DetailDrawer({ role, company, dm, onClose }) {
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

          {/* Decision Maker */}
          {dm && (
            <div style={{ marginTop:16, background:"#F7F7F8", borderRadius:8, padding:"14px 16px" }}>
              <div style={{ fontSize:11, fontWeight:600, color:"#A0A3A9", textTransform:"uppercase", letterSpacing:0.4, marginBottom:8 }}>Decision Maker</div>
              <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                <div style={{ width:36, height:36, borderRadius:8, background:"#EBEBED", display:"flex", alignItems:"center", justifyContent:"center", fontSize:14, fontWeight:700, color:"#6B6F76" }}>
                  {dm.name?.charAt(0) || "?"}
                </div>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:14, fontWeight:600, color:"#1A1A1A" }}>{dm.name}</div>
                  <div style={{ fontSize:12, color:"#6B6F76" }}>{dm.title}</div>
                </div>
                {dm.linkedin_url && (
                  <a href={dm.linkedin_url} target="_blank" rel="noopener" onClick={e=>e.stopPropagation()} style={{
                    padding:"5px 10px", borderRadius:5, background:"#0A66C2", color:"#fff",
                    fontSize:11, fontWeight:600, textDecoration:"none", whiteSpace:"nowrap",
                  }}>LinkedIn ↗</a>
                )}
              </div>
              {(dm.email || dm.phone) && (
                <div style={{ marginTop:10, display:"flex", gap:8, flexWrap:"wrap" }}>
                  {dm.email && (
                    <a href={`mailto:${dm.email}`} style={{ display:"inline-flex", alignItems:"center", gap:4, padding:"4px 10px", borderRadius:5, background:"#fff", border:"1px solid #EBEBED", fontSize:12, color:"#1A1A1A", textDecoration:"none", fontWeight:500 }}>
                      ✉ {dm.email}
                    </a>
                  )}
                  {dm.phone && (
                    <span style={{ display:"inline-flex", alignItems:"center", gap:4, padding:"4px 10px", borderRadius:5, background:"#fff", border:"1px solid #EBEBED", fontSize:12, color:"#1A1A1A", fontWeight:500 }}>
                      ☎ {dm.phone}
                    </span>
                  )}
                </div>
              )}
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

export default function ArteqCRM() {
  const [roles, setRoles] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState({});  // company_id → contact
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("roles");
  const [tierFilter, setTierFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key:"final_score", dir:"desc" });
  const [selected, setSelected] = useState(null);
  const cMap = useRef({});

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [c, r, cc] = await Promise.all([
        supaFetch("company","select=*&limit=1000"),
        supaFetch("role","select=*&limit=1000"),
        supaFetch("company_contact","select=*,contact:contact_id(*)&is_decision_maker=eq.true&limit=1000").catch(() => []),
      ]);
      setCompanies(c);
      const m = {}; c.forEach(co => { m[co.id] = co; }); cMap.current = m;
      setRoles(r);
      // Build company_id → decision maker contact map
      const dmMap = {};
      (cc || []).forEach(link => {
        if (link.contact) {
          dmMap[link.company_id] = link.contact;
        }
      });
      setContacts(dmMap);
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
            <span style={{ fontSize:15, fontWeight:600 }}>{tab === "roles" ? "Roles" : "Companies"}</span>
            <span style={{ fontSize:12, color:"#A0A3A9" }}>{tab === "roles" ? `${filtered.length} records` : `${filteredCompanies.length} records`}</span>
          </div>
          <button onClick={load} style={{
            padding:"5px 12px", borderRadius:6, border:"1px solid #EBEBED",
            background:"#fff", cursor:"pointer", fontSize:12, fontWeight:500,
            color:"#6B6F76", fontFamily:"inherit",
          }}>↻ Refresh</button>
        </div>

        {/* Filters */}
        {tab === "roles" ? (
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
          ) : (
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
                      <tr key={c.id} style={{ borderBottom:"1px solid #F7F7F8" }}
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
          )}
        </div>
      </div>

      {tab === "roles" && selected && <DetailDrawer role={selected} company={cMap.current[selected.company_id]} dm={contacts[selected.company_id]} onClose={()=>setSelected(null)} />}
    </div>
  );
}
