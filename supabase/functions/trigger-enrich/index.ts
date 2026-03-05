/**
 * Supabase Edge Function: Trigger Company Enrichment
 *
 * Receives a company_id and dispatches a GitHub Actions workflow
 * to run enrich_single.py for that company.
 *
 * Setup:
 * 1. Create GitHub PAT with `repo` scope: github.com/settings/tokens
 * 2. supabase secrets set GITHUB_PAT=ghp_...
 * 3. supabase functions deploy trigger-enrich
 */

const GITHUB_PAT = Deno.env.get("GITHUB_PAT") || "";
const GITHUB_REPO = "nuls361/arteq-scraper";
const WORKFLOW_FILE = "enrich_company.yml";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, apikey",
};

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  if (!GITHUB_PAT) {
    console.error("GITHUB_PAT not configured");
    return new Response(JSON.stringify({ error: "GitHub PAT not configured" }), {
      status: 500,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  let body: { company_id?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const companyId = body.company_id;
  if (!companyId) {
    return new Response(JSON.stringify({ error: "company_id is required" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  console.log(`Triggering enrichment for company ${companyId}`);

  // Dispatch GitHub Actions workflow
  const dispatchUrl = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`;

  try {
    const resp = await fetch(dispatchUrl, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${GITHUB_PAT}`,
        Accept: "application/vnd.github.v3+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { company_id: companyId },
      }),
    });

    if (resp.status === 204) {
      console.log(`Workflow dispatched successfully for ${companyId}`);
      return new Response(JSON.stringify({ ok: true, company_id: companyId }), {
        status: 200,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      });
    }

    const errorText = await resp.text();
    console.error(`GitHub API error: ${resp.status} — ${errorText}`);
    return new Response(
      JSON.stringify({ error: "GitHub dispatch failed", status: resp.status, detail: errorText }),
      {
        status: 502,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      }
    );
  } catch (e) {
    console.error(`Dispatch error: ${e}`);
    return new Response(JSON.stringify({ error: "Dispatch failed" }), {
      status: 500,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }
});
