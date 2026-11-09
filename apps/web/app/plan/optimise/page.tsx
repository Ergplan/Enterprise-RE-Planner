import { redirect } from "next/navigation";

export default async function OptimiseRedirect({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  redirect(c ? `/results?c=${c}` : "/");
}
