import { redirect } from "next/navigation";

/** Legacy Chat route: the formal new-task entry is the Discover page. */
export default function Page() {
  redirect("/");
}
