import crypto from "crypto";

/** Matches the previous Python backend's algorithm exactly (sha256 of
 * "salt:author") so existing hashed authors in the real database stay
 * consistent if this is ever cross-checked. */
export function hashAuthor(author: string): string {
  const salt = process.env.AUTHOR_HASH_SALT || "change-me-in-prod";
  return crypto.createHash("sha256").update(`${salt}:${author}`, "utf-8").digest("hex");
}

/** Matches the previous Python backend's normalise-then-hash algorithm
 * (NFKC normalize, trim, lowercase, collapse whitespace) so exact-duplicate
 * detection behaves the same way against already-ingested real reviews. */
export function contentHash(text: string): string {
  const normalised = text.normalize("NFKC").trim().toLowerCase().replace(/\s+/g, " ");
  return crypto.createHash("sha256").update(normalised, "utf-8").digest("hex");
}
