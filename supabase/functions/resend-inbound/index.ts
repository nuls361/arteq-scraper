/**
 * Supabase Edge Function: Resend Inbound Email Webhook
 *
 * Receives inbound emails from Resend, matches them to existing outreach threads,
 * and stores them in the outreach table for the orchestrator to process.
 *
 * Setup:
 * 1. Deploy: supabase functions deploy resend-inbound
 * 2. Set secret: supabase secrets set RESEND_WEBHOOK_SECRET=whsec_...
 * 3. In Resend Dashboard → Webhooks → Add endpoint:
 *    URL: https://<project>.supabase.co/functions/v1/resend-inbound
 *    Events: email.received (inbound)
 * 4. Configure MX record for your domain to point to Resend's inbound servers
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { crypto } from "https://deno.land/std@0.208.0/crypto/mod.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const WEBHOOK_SECRET = Deno.env.get("RESEND_WEBHOOK_SECRET") || "";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

interface ResendInboundPayload {
  type: "email.received";
  data: {
    from: string;
    to: string[];
    subject: string;
    html?: string;
    text?: string;
    headers?: { name: string; value: string }[];
    created_at: string;
  };
}

async function verifyWebhook(
  body: string,
  signature: string | null
): Promise<boolean> {
  if (!WEBHOOK_SECRET || !signature) return !WEBHOOK_SECRET; // Skip if no secret configured

  try {
    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
      "raw",
      encoder.encode(WEBHOOK_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const sig = await crypto.subtle.sign(
      "HMAC",
      key,
      encoder.encode(body)
    );
    const expectedSig = Array.from(new Uint8Array(sig))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    return signature === expectedSig;
  } catch {
    return false;
  }
}

function extractEmail(from: string): string {
  const match = from.match(/<([^>]+)>/);
  return match ? match[1].toLowerCase() : from.toLowerCase().trim();
}

function extractReplySubject(subject: string): string {
  return subject.replace(/^(re:\s*|aw:\s*|fwd:\s*)+/gi, "").trim();
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const body = await req.text();
  const signature = req.headers.get("resend-signature");

  // Verify webhook signature
  if (WEBHOOK_SECRET && !(await verifyWebhook(body, signature))) {
    console.error("Invalid webhook signature");
    return new Response("Invalid signature", { status: 401 });
  }

  let payload: ResendInboundPayload;
  try {
    payload = JSON.parse(body);
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  if (payload.type !== "email.received") {
    return new Response("OK — ignored event type", { status: 200 });
  }

  const email = payload.data;
  const senderEmail = extractEmail(email.from);
  const cleanSubject = extractReplySubject(email.subject);
  const replyText = email.text || "";
  const replyHtml = email.html || `<p>${replyText}</p>`;

  console.log(`Inbound email from ${senderEmail}: ${email.subject}`);

  // Find matching outreach thread by sender email
  // Look for outreach where the contact's email matches the sender
  const { data: matchingContacts } = await supabase
    .from("contact")
    .select("id")
    .eq("email", senderEmail)
    .limit(5);

  if (!matchingContacts || matchingContacts.length === 0) {
    console.log(`No matching contact for ${senderEmail} — storing as unmatched`);
    // Store anyway for manual review
    await supabase.from("outreach").insert({
      subject: email.subject,
      body_html: replyHtml,
      raw_text: replyText,
      direction: "inbound",
      from_email: senderEmail,
      status: "replied",
    });
    return new Response("OK — stored unmatched", { status: 200 });
  }

  const contactIds = matchingContacts.map((c: { id: string }) => c.id);

  // Find the most recent outreach thread to this contact
  const { data: existingOutreach } = await supabase
    .from("outreach")
    .select("id, thread_id, company_id, contact_id, subject")
    .in("contact_id", contactIds)
    .eq("direction", "outbound")
    .order("created_at", { ascending: false })
    .limit(1);

  let threadId: string | null = null;
  let companyId: string | null = null;
  let contactId: string | null = null;
  let inReplyTo: string | null = null;

  if (existingOutreach && existingOutreach.length > 0) {
    const original = existingOutreach[0];
    threadId = original.thread_id || original.id;
    companyId = original.company_id;
    contactId = original.contact_id;
    inReplyTo = original.id;

    // Mark original as got_reply
    await supabase
      .from("outreach")
      .update({ got_reply: true })
      .eq("id", original.id);

    console.log(`Matched to thread ${threadId} (company: ${companyId})`);
  } else {
    contactId = contactIds[0];
    console.log(`No outreach thread found — storing as new inbound`);
  }

  // Store the inbound reply
  const { error } = await supabase.from("outreach").insert({
    company_id: companyId,
    contact_id: contactId,
    subject: email.subject,
    body_html: replyHtml,
    raw_text: replyText,
    direction: "inbound",
    thread_id: threadId,
    in_reply_to: inReplyTo,
    from_email: senderEmail,
    status: "replied", // Orchestrator will process and change to 'answered'
  });

  if (error) {
    console.error("Insert error:", error);
    return new Response("Insert error", { status: 500 });
  }

  // Log the reply in agent_log
  if (companyId) {
    await supabase.from("agent_log").insert({
      action: "inbound_reply",
      entity_type: "company",
      entity_id: companyId,
      reason: `Reply from ${senderEmail}: ${cleanSubject}`,
      metadata: { sender: senderEmail, subject: email.subject },
    });

    // Add dossier entry
    await supabase.from("company_dossier").insert({
      company_id: companyId,
      entry_type: "outreach",
      title: `Reply received: ${email.subject}`,
      content: `From: ${senderEmail}\n\n${replyText.slice(0, 500)}`,
      source: "resend-inbound",
      author: senderEmail,
    });
  }

  return new Response("OK — reply stored", { status: 200 });
});
