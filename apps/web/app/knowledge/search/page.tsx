import { connection } from "next/server";
import { KnowledgeSearchPage } from "@/features/knowledge/search/KnowledgeSearchPage";

export default async function Page() {
  // Keep the initial RSC query aligned with the requested URL. A static shell
  // can seed Next's empty-search route cache with a query-bearing canonical URL.
  await connection();
  return <KnowledgeSearchPage />;
}
