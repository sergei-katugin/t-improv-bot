import type { Attendees } from "../types";

export const previewAttendees: Attendees = {
  occupied: 6, maxSeats: 50, arrived: 3, hasMore: false, nextOffset: 100,
  registrations: [
    { id: 1, name: "Анна Смирнова", guests: 1, username: "anna_impro", confirmed: true, checkedInCount: 2, source: "telegram" },
    { id: 2, name: "Михаил Орлов", guests: 0, username: "m_orlov", confirmed: null, checkedInCount: 0, source: "telegram" },
  ],
  manual: [{ id: 11, name: "Елена", contact: "@elena_cy", guests: 1, checkedInCount: 1, source: "manual" }],
  waitlist: [{ id: 21, name: "Олег", username: "oleg_impro", position: 1 }],
};
