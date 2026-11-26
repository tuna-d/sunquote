import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/api/client";
import { PROBLEM_TYPES } from "@/api/problem";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { QuoteForm } from "./QuoteForm";

const QUOTE_ID = "6f1c1a52-0d3c-4b7e-9a57-3c1f5f0d2a11";

interface Call {
  url: string;
  body: Record<string, unknown>;
}

/** A client over a fake `fetch`: every request is recorded, `answer` decides the response. */
function fakeApi(answer: (call: Call) => Response | Promise<Response> = () => created()) {
  const calls: Call[] = [];
  const client = createApiClient({
    baseUrl: "http://api.test",
    fetch: async (request) => {
      const call = { url: request.url, body: (await request.json()) as Record<string, unknown> };
      calls.push(call);
      return answer(call);
    },
  });
  return { client, calls };
}

function created(id = QUOTE_ID): Response {
  return new Response(JSON.stringify({ id }), {
    status: 201,
    headers: { "content-type": "application/json" },
  });
}

function problem(
  type: string,
  status: number,
  extra: Record<string, unknown> = {},
  headers: Record<string, string> = {},
): Response {
  return new Response(
    JSON.stringify({ type, title: "Başlık", status, detail: "English detail", ...extra }),
    { status, headers: { "content-type": "application/problem+json", ...headers } },
  );
}

function setup(answer?: (call: Call) => Response | Promise<Response>) {
  const api = fakeApi(answer);
  const user = userEvent.setup();
  render(<QuoteForm client={api.client} />);
  return { ...api, user };
}

type User = ReturnType<typeof userEvent.setup>;

/** Fills every required field with a valid pitched-roof, Address, kWh Quote. */
async function fillValid(user: User) {
  await user.type(screen.getByLabelText(/Müşteri adı/), "Elif Yıldırım");
  await user.type(screen.getByRole("textbox", { name: /^Adres/ }), "Kavaklıdere Mah., Çankaya, Ankara");
  await user.click(screen.getByRole("radio", { name: "Güney" }));
  await user.type(screen.getByLabelText(/^Eğim\b/), "30");
  await user.type(screen.getByLabelText(/Kullanılabilir alan/), "62");
  await user.type(screen.getByLabelText(/Aylık tüketim/), "520");
}

const submit = (user: User) => user.click(screen.getByRole("button", { name: /Teklifi oluştur/ }));

beforeEach(() => {
  push.mockClear();
});

describe("the demo banner", () => {
  it("warns that the demo is public above the fields", () => {
    setup();

    expect(screen.getByRole("note", { name: "Herkese açık demo" })).toBeInTheDocument();
  });
});

describe("the Roof fields", () => {
  it("asks for azimuth and tilt on a pitched Roof, the starting choice", () => {
    setup();

    expect(screen.getByRole("radio", { name: "Eğimli" })).toBeChecked();
    expect(screen.getByLabelText(/Yön \(azimut\)/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Eğim\b/)).toBeInTheDocument();
  });

  it("drops azimuth and tilt for a flat Roof and says why", async () => {
    const { user } = setup();

    await user.click(screen.getByRole("radio", { name: "Düz" }));

    expect(screen.queryByLabelText(/Yön \(azimut\)/)).toBeNull();
    expect(screen.queryByLabelText(/^Eğim\b/)).toBeNull();
    expect(screen.getByText(/yön ve eğim sorulmaz/)).toBeInTheDocument();
  });

  it("keeps what was typed when the Sales Rep flips to flat and back", async () => {
    const { user } = setup();
    await user.type(screen.getByLabelText(/^Eğim\b/), "35");

    await user.click(screen.getByRole("radio", { name: "Düz" }));
    await user.click(screen.getByRole("radio", { name: "Eğimli" }));

    expect(screen.getByLabelText(/^Eğim\b/)).toHaveValue("35");
  });
});

describe("the compass picker", () => {
  it("sets the degrees from a compass point", async () => {
    const { user } = setup();

    await user.click(screen.getByRole("radio", { name: "Güneybatı" }));

    expect(screen.getByLabelText(/Yön \(azimut\)/)).toHaveValue("225");
    expect(screen.getByRole("status")).toHaveTextContent("225° · Güneybatı");
  });

  it("accepts degrees, names the nearest point and selects it when exact", async () => {
    const { user } = setup();
    const degrees = screen.getByLabelText(/Yön \(azimut\)/);

    await user.type(degrees, "200");
    expect(screen.getByRole("status")).toHaveTextContent("200° · en yakın yön: Güney");
    expect(screen.getByRole("radio", { name: "Güney" })).not.toBeChecked();

    await user.clear(degrees);
    await user.type(degrees, "180");
    expect(screen.getByRole("radio", { name: "Güney" })).toBeChecked();
  });

  it("accepts a decimal comma in the degrees", async () => {
    const { user } = setup();

    await user.type(screen.getByLabelText(/Yön \(azimut\)/), "187,5");

    expect(screen.getByRole("status")).toHaveTextContent("187,5° · en yakın yön: Güney");
  });

  it("says nothing about a direction before one is given", () => {
    setup();

    expect(screen.getByRole("status")).toHaveTextContent("—");
  });
});

describe("the Site: Address or Coordinates", () => {
  it("asks for an Address first and for latitude and longitude on request", async () => {
    const { user } = setup();
    expect(screen.getByRole("radio", { name: "Adres" })).toBeChecked();
    expect(screen.getByRole("textbox", { name: /^Adres/ })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Enlem/)).toBeNull();

    await user.click(screen.getByRole("radio", { name: "Koordinat" }));

    expect(screen.queryByRole("textbox", { name: /^Adres/ })).toBeNull();
    expect(screen.getByLabelText(/Enlem/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Boylam/)).toBeInTheDocument();
  });
});

describe("the consumption: kWh or a Monthly Bill", () => {
  it("asks for kWh first and for the bill on request", async () => {
    const { user } = setup();
    expect(screen.getByRole("radio", { name: "Aylık kWh" })).toBeChecked();
    expect(screen.getByLabelText(/Aylık tüketim/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Aylık fatura tutarı/)).toBeNull();

    await user.click(screen.getByRole("radio", { name: "Aylık fatura" }));

    expect(screen.queryByLabelText(/Aylık tüketim/)).toBeNull();
    expect(screen.getByLabelText(/Aylık fatura tutarı/)).toBeInTheDocument();
  });

  it("offers only the residential Subscriber Group", () => {
    setup();

    const group = screen.getByLabelText(/Abone grubu/);
    expect(within(group).getAllByRole("option")).toHaveLength(1);
    expect(group).toHaveValue("residential");
  });
});

describe("client validation, with the API's bounds", () => {
  it("explains every missing required field and sends nothing", async () => {
    const { user, calls } = setup();

    await submit(user);

    expect(calls).toHaveLength(0);
    expect(screen.getByRole("alert")).toHaveTextContent("6 alanı düzeltin");
    expect(screen.getAllByText("Müşteri adı gerekli.")).toHaveLength(2);
    expect(screen.getAllByText(/Adres gerekli/)).toHaveLength(2);
    expect(screen.getAllByText("Yön gerekli.")).toHaveLength(2);
    expect(screen.getAllByText("Eğim gerekli.")).toHaveLength(2);
    expect(screen.getAllByText("Kullanılabilir alan gerekli.")).toHaveLength(2);
    expect(screen.getAllByText("Aylık tüketim gerekli.")).toHaveLength(2);
  });

  it("marks the field, ties the message to it and moves focus to the first one", async () => {
    const { user } = setup();

    await submit(user);

    const name = screen.getByLabelText(/Müşteri adı/);
    expect(name).toHaveFocus();
    expect(name).toBeInvalid();
    expect(name).toHaveAccessibleDescription("Müşteri adı gerekli.");
  });

  it("clears a field's error once the Sales Rep edits it", async () => {
    const { user } = setup();
    await submit(user);

    await user.type(screen.getByLabelText(/Müşteri adı/), "E");

    expect(screen.getByLabelText(/Müşteri adı/)).toBeValid();
    expect(screen.queryByText("Müşteri adı gerekli.")).toBeNull();
  });

  it.each([
    ["azimuth 360 (the bound is below 360)", /Yön \(azimut\)/, "360", /Yön 0 ile 360/],
    ["azimuth below 0", /Yön \(azimut\)/, "-1", /Yön 0 ile 360/],
    ["tilt above 90", /^Eğim\b/, "91", "Eğim 0 ile 90 derece arasında olmalı."],
    ["a zero Usable Area", /Kullanılabilir alan/, "0", "Kullanılabilir alan 0’dan büyük olmalı."],
    ["a negative consumption", /Aylık tüketim/, "-3", "Aylık tüketim 0’dan büyük olmalı."],
    ["a Contracted Power of 0", /Sözleşme gücü/, "0", "Sözleşme gücü 0’dan büyük olmalı."],
    ["text instead of a number", /Kullanılabilir alan/, "çok", /Sayı yazın/],
  ])("rejects %s", async (_name, label, value, message) => {
    const { user, calls } = setup();
    await fillValid(user);
    const input = screen.getByLabelText(label);
    await user.clear(input);
    await user.type(input, value);

    await submit(user);

    expect(calls).toHaveLength(0);
    expect(screen.getAllByText(message)).toHaveLength(2);
  });

  it.each([
    ["latitude above 90", "Enlem", "91", "Enlem −90 ile 90 arasında olmalı."],
    ["longitude below -180", "Boylam", "-181", "Boylam −180 ile 180 arasında olmalı."],
  ])("rejects %s", async (_name, label, value, message) => {
    const { user, calls } = setup();
    await fillValid(user);
    await user.click(screen.getByRole("radio", { name: "Koordinat" }));
    await user.type(screen.getByLabelText(/Enlem/), label === "Enlem" ? value : "39,9");
    await user.type(screen.getByLabelText(/Boylam/), label === "Boylam" ? value : "32,8");

    await submit(user);

    expect(calls).toHaveLength(0);
    expect(screen.getAllByText(message)).toHaveLength(2);
  });

  it("accepts the bounds themselves: azimuth 0 and tilt 90", async () => {
    const { user, calls } = setup();
    await fillValid(user);
    const azimuth = screen.getByLabelText(/Yön \(azimut\)/);
    await user.clear(azimuth);
    await user.type(azimuth, "0");
    const tilt = screen.getByLabelText(/^Eğim\b/);
    await user.clear(tilt);
    await user.type(tilt, "90");

    await submit(user);

    expect(calls).toHaveLength(1);
  });

  it("does not ask for azimuth or tilt of a flat Roof", async () => {
    const { user, calls } = setup();
    await user.type(screen.getByLabelText(/Müşteri adı/), "Elif Yıldırım");
    await user.type(screen.getByRole("textbox", { name: /^Adres/ }), "Ankara");
    await user.click(screen.getByRole("radio", { name: "Düz" }));
    await user.type(screen.getByLabelText(/Kullanılabilir alan/), "80");
    await user.type(screen.getByLabelText(/Aylık tüketim/), "300");

    await submit(user);

    expect(calls).toHaveLength(1);
  });

  it("checks the optional email's shape and the name's length", async () => {
    const { user, calls } = setup();
    await fillValid(user);
    await user.type(screen.getByLabelText(/E-posta/), "elif.example.com");
    await user.type(screen.getByLabelText(/Müşteri adı/), "x".repeat(200));

    await submit(user);

    expect(calls).toHaveLength(0);
    expect(screen.getAllByText("E-posta adresi geçerli değil.")).toHaveLength(2);
    expect(screen.getAllByText("Müşteri adı en fazla 200 karakter olabilir.")).toHaveLength(2);
  });
});

describe("the request", () => {
  it("posts an Address Quote on a pitched Roof with kWh, numbers as decimal strings", async () => {
    const { user, calls } = setup();
    await fillValid(user);
    await user.type(screen.getByLabelText(/Telefon/), "+90 532 000 00 00");
    await user.type(screen.getByLabelText(/Sözleşme gücü/), "7,5");

    await submit(user);

    expect(calls).toEqual([
      {
        url: "http://api.test/quotes",
        body: {
          customer: { name: "Elif Yıldırım", phone: "+90 532 000 00 00" },
          site: { address: "Kavaklıdere Mah., Çankaya, Ankara" },
          roof: { roof_type: "pitched", usable_area_m2: "62", azimuth_deg: "180", tilt_deg: "30" },
          consumption: { monthly_consumption_kwh: "520" },
          subscriber_group: "residential",
          contracted_power_kw: "7.5",
        },
      },
    ]);
  });

  it("posts Coordinates instead of the Address, a flat Roof without angles and a bill without kWh", async () => {
    const { user, calls } = setup();
    await user.type(screen.getByLabelText(/Müşteri adı/), "  Elif Yıldırım  ");
    await user.type(screen.getByRole("textbox", { name: /^Adres/ }), "Ankara");
    await user.click(screen.getByRole("radio", { name: "Koordinat" }));
    await user.type(screen.getByLabelText(/Enlem/), "39,9031");
    await user.type(screen.getByLabelText(/Boylam/), "32,8597");
    await user.click(screen.getByRole("radio", { name: "Düz" }));
    await user.type(screen.getByLabelText(/Kullanılabilir alan/), "80,5");
    await user.click(screen.getByRole("radio", { name: "Aylık fatura" }));
    await user.type(screen.getByLabelText(/Aylık fatura tutarı/), "2400");

    await submit(user);

    expect(calls[0]?.body).toEqual({
      customer: { name: "Elif Yıldırım" },
      site: { latitude: "39.9031", longitude: "32.8597" },
      roof: { roof_type: "flat", usable_area_m2: "80.5" },
      consumption: { monthly_bill_try: "2400" },
      subscriber_group: "residential",
    });
  });

  it("goes to the new Quote's page on success", async () => {
    const { user } = setup();
    await fillValid(user);

    await submit(user);

    expect(push).toHaveBeenCalledWith(`/quotes/${QUOTE_ID}`);
  });

  it("holds the button while the Quote is being made, so it cannot be sent twice", async () => {
    let release: (response: Response) => void = () => undefined;
    const { user, calls } = setup(
      () => new Promise<Response>((resolve) => (release = resolve)),
    );
    await fillValid(user);

    await submit(user);

    const button = screen.getByRole("button", { name: /Teklif hazırlanıyor/ });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(calls).toHaveLength(1);

    release(created());
    await vi.waitFor(() => expect(push).toHaveBeenCalledTimes(1));
  });
});

describe("what the API says is wrong", () => {
  it("maps a validation problem to its fields", async () => {
    const { user } = setup(() =>
      problem(PROBLEM_TYPES.validation, 422, {
        errors: [
          { field: "customer.email", message: "value is not a valid email address" },
          { field: "roof.usable_area_m2", message: "Input should be greater than 0" },
        ],
      }),
    );
    await fillValid(user);

    await submit(user);

    expect(await screen.findAllByText("E-posta adresi geçerli değil.")).toHaveLength(2);
    expect(screen.getByLabelText(/E-posta/)).toBeInvalid();
    expect(screen.getByLabelText(/Kullanılabilir alan/)).toBeInvalid();
    expect(screen.getByLabelText(/Kullanılabilir alan/)).toHaveAccessibleDescription(
      "Kullanılabilir alan geçerli değil.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("2 alanı düzeltin");
    expect(push).not.toHaveBeenCalled();
  });

  it("lists a validation error it has no field for instead of dropping it", async () => {
    const { user } = setup(() =>
      problem(PROBLEM_TYPES.validation, 422, {
        errors: [{ field: "body", message: "malformed" }],
      }),
    );
    await fillValid(user);

    await submit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Form gönderilemedi");
  });

  it("puts 'Address not found' on the Address field and suggests Coordinates", async () => {
    const { user } = setup(() => problem(PROBLEM_TYPES.addressNotFound, 422));
    await fillValid(user);

    await submit(user);

    expect(await screen.findAllByText(/Adres bulunamadı/)).toHaveLength(2);
    expect(screen.getByRole("textbox", { name: /^Adres/ })).toBeInvalid();
    expect(screen.getByRole("textbox", { name: /^Adres/ })).toHaveFocus();
    expect(screen.getByRole("alert")).toHaveTextContent("koordinat");
  });

  it("puts 'unsupported Subscriber Group' on that field", async () => {
    const { user } = setup(() => problem(PROBLEM_TYPES.unsupportedSubscriberGroup, 422));
    await fillValid(user);

    await submit(user);

    expect(await screen.findAllByText(/desteklenmiyor/)).toHaveLength(2);
    expect(screen.getByLabelText(/Abone grubu/)).toBeInvalid();
  });

  it.each([
    [PROBLEM_TYPES.noViableSystem, 422, /uygun bir sistem çıkmadı/],
    [PROBLEM_TYPES.noCompatibleInverter, 422, /uyumlu inverter/],
    [PROBLEM_TYPES.locationNotSupported, 422, /konum desteklenmiyor/],
    [PROBLEM_TYPES.upstreamUnavailable, 503, /şu an ulaşılamıyor/],
  ])("shows its own Turkish message for %s", async (type, status, message) => {
    const { user } = setup(() => problem(type, status));
    await fillValid(user);

    await submit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).not.toHaveTextContent("English detail");
  });

  it("tells the Sales Rep how long to wait when rate-limited", async () => {
    const { user } = setup(() =>
      problem(PROBLEM_TYPES.rateLimited, 429, {}, { "Retry-After": "1800" }),
    );
    await fillValid(user);

    await submit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Çok fazla teklif");
    expect(alert).toHaveTextContent("30 dakika");
  });

  it("still explains a rate limit that came without Retry-After", async () => {
    const { user } = setup(() => problem(PROBLEM_TYPES.rateLimited, 429));
    await fillValid(user);

    await submit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Çok fazla teklif");
  });

  it("explains a network failure", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetch: async () => {
        throw new TypeError("fetch failed");
      },
    });
    const user = userEvent.setup();
    render(<QuoteForm client={client} />);
    await fillValid(user);

    await submit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Sunucuya ulaşılamadı");
  });

  it("explains a failure that is not a problem document", async () => {
    const { user } = setup(
      () => new Response("Bad gateway", { status: 502, headers: { "content-type": "text/plain" } }),
    );
    await fillValid(user);

    await submit(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Beklenmeyen bir hata");
  });

  it("lets the Sales Rep try again after a failure", async () => {
    let attempt = 0;
    const { user, calls } = setup(() =>
      ++attempt === 1 ? problem(PROBLEM_TYPES.upstreamUnavailable, 503) : created(),
    );
    await fillValid(user);
    await submit(user);
    await screen.findByRole("alert");

    await submit(user);

    expect(calls).toHaveLength(2);
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith(`/quotes/${QUOTE_ID}`));
  });
});
