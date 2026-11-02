// How this plugin's page draws its tasks' outputs: the trip as a card of facts, the flight offers as a
// table, and a booking as the chosen offer or the reason nothing was booked.
import { dataTable, h, plural, statusPill } from "./kit/components.js";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;
const yesNo = (value) => (value ? "Yes" : "No");
const place = (airport) => `${airport.code} · ${airport.city}, ${airport.country} (${airport.continent})`;

function facts(rows) {
  return h(
    "dl",
    { class: "trip-facts" },
    rows.map(([label, value]) => [h("dt", { text: label }), h("dd", { text: value })]),
  );
}

function tripCard(run_id, trip) {
  const dates = trip.date_mode === "FIXED" ? trip.date_from : `${trip.date_from} to ${trip.date_to} (flexible)`;
  return h(
    "div",
    { class: "trip-card" },
    h("h4", { text: `${trip.traveller_name}: ${trip.origin.code} → ${trip.destination.code}` }),
    facts([
      ["Traveller", trip.traveller_type.replace("_", " ").toLowerCase()],
      ["From", place(trip.origin)],
      ["To", place(trip.destination)],
      ["Booked on", trip.booking_date],
      ["Departs", dates],
      ["Business requested", yesNo(trip.wants_business)],
      ["Checked bag", yesNo(trip.wants_checked_bag)],
      ["Seed", String(trip.seed)],
      ["Run", run_id || "none"],
    ]),
  );
}

function route(offer) {
  const stops = offer.segments.map((segment) => segment.origin).concat(offer.segments.at(-1).destination);
  return stops.join(" → ");
}

function offersTable(offers) {
  const table = dataTable({
    columns: [
      { key: "offer_id", label: "Offer", primary: true },
      { key: "depart", label: "Departs", value: (o) => o.segments[0].depart },
      { key: "route", label: "Route", value: route },
      { key: "carrier", label: "Carrier" },
      { key: "operator", label: "Operator", value: (o) => o.operator.toLowerCase() },
      { key: "cabin", label: "Cabin", value: (o) => o.cabin.toLowerCase() },
      { key: "fare_cents", label: "Fare", numeric: true, render: (o) => money(o.fare_cents) },
      { key: "total_air_minutes", label: "Air min", numeric: true },
      { key: "bags", label: "Bag fees", value: (o) => o.segments.map((s) => money(s.bag_fee_cents)).join(" + ") },
    ],
    rows: offers,
    sort: { key: "depart" },
    caption: "Flight offers",
    empty: "No offers on this route and these days.",
  });
  return table.element;
}

export default {
  TripOutput: ({ run_id, trip }) => tripCard(run_id, trip),
  SearchOutput: ({ offers }) =>
    h("div", { class: "offers" }, h("p", { class: "muted", text: plural(offers.length, "offer") }), offersTable(offers)),
  BookingOutput: (booking) =>
    booking.booked
      ? h(
          "div",
          { class: "booking" },
          statusPill(`Booked ${booking.offer_id}`, "ok", { icon: true }),
          facts([
            ["Traveller pays for the bag", money(booking.traveller_out_of_pocket_cents)],
            ["Run", booking.run_id],
          ]),
        )
      : h(
          "div",
          { class: "booking" },
          statusPill("Not booked", "warn", { icon: true }),
          facts([
            ["Reason", booking.refusal === "CONSULTANT" ? "Consultant travel is not billed to the company" : "No compliant flight"],
            ["Run", booking.run_id],
          ]),
        ),
};
