import Link from "next/link";
import { notFound } from "next/navigation";
import { VersionEditor } from "@/components/rulebook/VersionEditor";
import { apiOrNull } from "@/lib/api";
import type { VersionDetail } from "@/lib/rulebook";

export const dynamic = "force-dynamic";

export default async function VersionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [detail, families] = await Promise.all([
    apiOrNull<VersionDetail>(`/rulebooks/versions/${id}`),
    apiOrNull<Record<string, { properties: { body: Record<string, unknown> } }>>("/rulebooks/families"),
  ]);
  if (!detail) notFound();
  return (
    <>
      <div className="eg-crumbs">
        <Link href="/rulebooks" className="eg-muted">Rulebooks</Link>
        <span data-icon="chevron-right" data-size="14"></span> <b>{detail.version.jurisdiction_id.toUpperCase()}</b>
      </div>
      <VersionEditor initial={detail} bodySchema={families?.[detail.version.family]?.properties?.body} />
    </>
  );
}
