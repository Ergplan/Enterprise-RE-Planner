import { redirect } from "next/navigation";

// The old step 1 lives in the Evaluate page now.
export default async function IntakeRedirect({ searchParams }: { searchParams: Promise<{ c?: string }> }) {
  const { c } = await searchParams;
  redirect(c ? `/evaluate?c=${c}` : "/evaluate");
}
