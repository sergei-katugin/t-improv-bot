export type Show = {
  id: number;
  title: string;
  teamName: string;
  showDateLabel: string;
  showDateLocal?: string;
  location: string;
  locationUrl?: string | null;
  city: string;
  isActive: boolean;
  maxSeats: number;
  occupiedSeats: number;
  registrarUsername: string | null;
  registrationUrl?: string;
  posterText?: string | null;
  feedbackEnabled?: boolean;
  checkinEnabled?: boolean;
  hasPoster?: boolean;
  registrationChatId?: number | null;
  registrationChatTitle?: string | null;
  registrationChatNameMode?: "short" | "full";
};

export type Options = {
  teams: { id: number; name: string; members: string | null }[];
  venues: { id: number; name: string; city: string; mapsUrl: string | null; defaultSeats: number }[];
  adChannels: { id: number; username: string; isActive: boolean }[];
};

export type Me = { id: number; firstName: string | null; username: string | null; role: "organizer" | "admin" };
export type RegistrationChatOption = { id: number; title: string; username: string | null; type: string };
export type AccessUser = { id: number; telegramId: number; username: string | null; firstName: string | null; lastName: string | null; role: "organizer" | "admin"; isCurrent: boolean; isProtected: boolean };
export type AuditItem = { id: number; action: string; entityType: string; entityId: number | null; details: Record<string, unknown> | null; createdAt: string; actor: { id: number; username: string | null; firstName: string | null; lastName: string | null; telegramId: number } | null };
export type ThemePreference = "system" | "light" | "dark";

export type Attendees = {
  occupied: number; maxSeats: number; arrived: number; hasMore: boolean; nextOffset: number;
  registrations: { id: number; name: string; guests: number; username: string | null; confirmed: boolean | null; checkedInCount: number; source: string | null }[];
  manual: { id: number; name: string; contact: string | null; checkedInCount: number; source: string | null }[];
};

export type Promotion = {
  html: string; text: string; registrationUrl: string; hasPoster: boolean; hasPublished: boolean;
  channels: { id: number; username: string; url: string }[];
};

export type Analytics = {
  registered: number; capacity: number; cancelledRegistrations: number; confirmed: number;
  arrived: number; checkinEnabled: boolean; feedbackEnabled: boolean; feedbackCount: number;
  averageRating: number; ratingDistribution: Record<string, number>;
  sources: { source: string; count: number }[];
  comments: { id: number; rating: number; comment: string; username: string | null; name: string | number; createdAt: string }[];
  commentsLimit: number;
};

export type ShowFormValue = {
  title: string; teamName: string; showDateLocal: string; location: string;
  locationUrl: string; city: string; posterText: string; maxSeats: number;
  registrarUsername: string; checkinEnabled: boolean; feedbackEnabled: boolean;
};
