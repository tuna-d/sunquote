import type { Metadata } from "next";

import { AssistantChat } from "@/components/AssistantChat";

export const metadata: Metadata = { title: "Asistan" };

export default function AssistantPage() {
  return <AssistantChat />;
}
