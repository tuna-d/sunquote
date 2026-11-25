import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AssistantResult } from "@/api/assistant";

import { AssistantChat } from "./AssistantChat";

type Send = (
  messages: { role: "user" | "assistant"; content: string }[],
) => Promise<AssistantResult>;

const question: AssistantResult = {
  ok: true,
  response: {
    reply: "Müşterinin adı ve adresi nedir?",
    quote: null,
    missing_fields: ["customer.name", "site.address"],
  },
};

const created: AssistantResult = {
  ok: true,
  response: {
    reply: "Teklifiniz hazır.",
    quote: {
      id: "11111111-1111-1111-1111-111111111111",
      quote_number: "SQ-2026-0042",
      document_url: "http://api.test/quotes/1/document",
    },
    missing_fields: [],
  },
};

async function say(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByRole("textbox", { name: /mesaj/i }), text);
  await user.click(screen.getByRole("button", { name: /gönder/i }));
}

describe("AssistantChat", () => {
  it("shows the reply and the Missing Fields as labelled chips under the question", async () => {
    const send = vi.fn<Send>().mockResolvedValue(question);
    render(<AssistantChat send={send} />);

    await say("Ankara için bir ev teklifi");

    expect(await screen.findByText("Müşterinin adı ve adresi nedir?")).toBeInTheDocument();
    const chips = screen.getByRole("list", { name: /eksik bilgiler/i });
    expect(within(chips).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Müşteri adı",
      "Adres",
    ]);
  });

  it("sends the whole conversation each time, oldest first", async () => {
    const send = vi.fn<Send>().mockResolvedValueOnce(question).mockResolvedValueOnce(created);
    render(<AssistantChat send={send} />);

    await say("Merhaba");
    await screen.findByText("Müşterinin adı ve adresi nedir?");
    await say("Elif, Ankara");

    expect(send).toHaveBeenLastCalledWith([
      { role: "user", content: "Merhaba" },
      { role: "assistant", content: "Müşterinin adı ve adresi nedir?" },
      { role: "user", content: "Elif, Ankara" },
    ]);
  });

  it("shows a created Quote as a card with links to the Quote and its document", async () => {
    render(<AssistantChat send={vi.fn<Send>().mockResolvedValue(created)} />);

    await say("Her şey burada");

    const card = await screen.findByRole("group", { name: /SQ-2026-0042/ });
    expect(within(card).getByRole("link", { name: /teklifi aç/i })).toHaveAttribute(
      "href",
      "/quotes/11111111-1111-1111-1111-111111111111",
    );
    expect(within(card).getByRole("link", { name: /belge/i })).toHaveAttribute(
      "href",
      "http://api.test/quotes/1/document",
    );
  });

  it("shows a pending state while the request runs and blocks a second send", async () => {
    let resolve!: (r: AssistantResult) => void;
    const send = vi.fn<Send>().mockReturnValue(new Promise((r) => (resolve = r)));
    render(<AssistantChat send={send} />);

    await say("Merhaba");

    expect(screen.getByRole("status")).toHaveTextContent(/yanıt hazırlanıyor/i);
    expect(screen.getByRole("button", { name: /gönder/i })).toBeDisabled();
    resolve(question);
    expect(await screen.findByText("Müşterinin adı ve adresi nedir?")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("enforces 2,000 characters per message and no empty message", async () => {
    render(<AssistantChat send={vi.fn<Send>()} />);
    const box = screen.getByRole("textbox", { name: /mesaj/i });
    expect(box).toHaveAttribute("maxlength", "2000");
    expect(screen.getByRole("button", { name: /gönder/i })).toBeDisabled();
    await userEvent.setup().type(box, "   ");
    expect(screen.getByRole("button", { name: /gönder/i })).toBeDisabled();
  });

  it("stops at 20 messages and offers a new conversation", async () => {
    const send = vi.fn<Send>().mockResolvedValue(question);
    render(<AssistantChat send={send} />);
    for (let i = 0; i < 10; i += 1) {
      await say(`mesaj ${i}`);
      await screen.findByText(`mesaj ${i}`);
      await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(i + 1));
      await vi.waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    }
    expect(screen.getByRole("textbox", { name: /mesaj/i })).toBeDisabled();
    expect(screen.getByText(/20 mesaj sınırına/i)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: /yeni konuşma/i }));
    expect(screen.getByRole("textbox", { name: /mesaj/i })).toBeEnabled();
    expect(screen.queryByText("Müşterinin adı ve adresi nedir?")).not.toBeInTheDocument();
  });

  it.each([
    [{ ok: false, kind: "not-configured" }, /yapılandırılmamış/i],
    [{ ok: false, kind: "unavailable" }, /şu anda yanıt veremiyor/i],
    [{ ok: false, kind: "budget-exhausted" }, /günlük.*sınır/i],
    [{ ok: false, kind: "rate-limited", retryAfterSeconds: 1800 }, /30 dakika/],
    [{ ok: false, kind: "rate-limited" }, /biraz sonra/i],
    [{ ok: false, kind: "network" }, /ulaşılamadı/i],
    [{ ok: false, kind: "error" }, /bir sorun oluştu/i],
  ] as [AssistantResult, RegExp][])(
    "explains %j in Turkish and keeps the message to retry",
    async (result, text) => {
      render(<AssistantChat send={vi.fn<Send>().mockResolvedValue(result)} />);

      await say("Merhaba");

      expect(await screen.findByRole("alert")).toHaveTextContent(text);
      expect(screen.getByRole("textbox", { name: /mesaj/i })).toHaveValue("Merhaba");
    },
  );

  it("shows the public-demo banner", () => {
    render(<AssistantChat send={vi.fn<Send>()} />);
    expect(screen.getByRole("note")).toHaveTextContent("Herkese açık demo");
  });
});
