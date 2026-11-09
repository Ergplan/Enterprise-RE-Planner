import { redirect } from "next/navigation";

export default async function SiteRedirect({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  redirect(c ? `/evaluate?c=${c}#sec-consumption` : "/evaluate");
}
