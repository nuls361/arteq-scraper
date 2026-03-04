-- ═══════════════════════════════════════════════════════════
-- Storage bucket for Company Dossier file uploads
-- Run this in Supabase SQL Editor AFTER 001_company_dossier.sql
-- ═══════════════════════════════════════════════════════════

-- Create storage bucket for dossier files
INSERT INTO storage.buckets (id, name, public)
VALUES ('dossier-files', 'dossier-files', true)
ON CONFLICT (id) DO NOTHING;

-- Allow public read access to dossier files
CREATE POLICY "Public read access for dossier files"
ON storage.objects FOR SELECT
USING (bucket_id = 'dossier-files');

-- Allow uploads via anon key
CREATE POLICY "Allow uploads for dossier files"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'dossier-files');
