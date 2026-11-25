import { expect, type Page, test } from "@playwright/test";

// The smoke test: a Sales Rep opens the form from the masthead, creates a Quote, lands on its
// page and finds it in the list. The API is `e2e/mock-api.mjs`.
//
// The mock answers `GET /quotes/{id}` with a 404 problem, so the first test only checks that the
// browser reaches the Quote's route; what the detail page shows is the detail ticket's own test.

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

/**
 * Waits until React has hydrated the form: it tags the DOM nodes it manages. A value typed
 * before that is wiped by hydration, which makes the test flaky on a cold dev server.
 */
async function waitForForm(page: Page) {
  await page.waitForFunction(() => {
    const form = document.querySelector("form");
    return form !== null && Object.keys(form).some((key) => key.startsWith("__reactFiber"));
  });
}

async function fillCustomerName(page: Page, name: string) {
  await waitForForm(page);
  await page.getByLabel(/Müşteri adı/).fill(name);
}

test("creates a Quote through the form, lands on its page and finds it in the list", async ({
  page,
}) => {
  const customer = `Elif Yıldırım ${Date.now()}`;

  await page.goto("/quotes");
  const nav = page.getByRole("navigation", { name: "Ana gezinme" });
  await nav.getByRole("link", { name: "Yeni teklif" }).click();
  await expect(page).toHaveURL(/\/quotes\/new$/);
  await expect(page.getByRole("note", { name: "Herkese açık demo" })).toBeVisible();

  await fillCustomerName(page, customer);
  await page.getByRole("textbox", { name: /^Adres/ }).fill("Kavaklıdere Mah., Çankaya, Ankara");
  await page.getByRole("radio", { name: "Güney", exact: true }).check();
  await page.getByLabel(/^Eğim\b/).fill("30");
  await page.getByLabel(/Kullanılabilir alan/).fill("62");
  await page.getByLabel(/Aylık tüketim/).fill("520");
  await page.getByRole("button", { name: /Teklifi oluştur/ }).click();

  await expect(page).toHaveURL(new RegExp(`/quotes/${UUID}$`));

  await nav.getByRole("link", { name: "Teklifler" }).click();
  await expect(page).toHaveURL(/\/quotes$/);
  await expect(page.getByRole("link", { name: customer })).toBeVisible();
});

test("explains a problem the API answers with, on the field it belongs to", async ({ page }) => {
  await page.goto("/quotes/new");
  await fillCustomerName(page, "Elif Yıldırım");
  const address = page.getByRole("textbox", { name: /^Adres/ });
  await address.fill("Atlantis");
  await page.getByRole("radio", { name: "Düz", exact: true }).check();
  await page.getByLabel(/Kullanılabilir alan/).fill("80");
  await page.getByLabel(/Aylık tüketim/).fill("300");
  await page.getByRole("button", { name: /Teklifi oluştur/ }).click();

  await expect(address).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("form").getByRole("alert")).toContainText("Adres bulunamadı");
  await expect(page).toHaveURL(/\/quotes\/new$/);
});
