import type { components, paths } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["UserOut"];
export type UserRole = Schemas["UserRole"];
export type Unit = Schemas["UnitOut"];
export type UserCreate = Schemas["UserCreate"];
export type UserUpdate = Schemas["UserUpdate"];
export type UnitCreate = Schemas["UnitCreate"];
export type UnitUpdate = Schemas["UnitUpdate"];
export type UnitRef = Schemas["UnitRef"];
export type Device = Schemas["DeviceOut"];
export type DeviceDetail = Schemas["DeviceDetail"];
export type DeviceStatus = Schemas["DeviceStatus"];
export type EventType = Schemas["EventType"];
export type TimelineEvent = Schemas["TimelineEvent"];
export type Timeline = Schemas["Timeline"];
export type EventOut = Schemas["EventOut"];
export type PendingAcknowledgement = Schemas["PendingAcknowledgement"];
export type AckStatus = Schemas["AckStatus"];
export type Report = Schemas["Report"];
export type Section = Schemas["Section"];
export type ComplaintOut = Schemas["ComplaintOut"];
export type ComplaintStatus = Schemas["ComplaintStatus"];
export type ComplaintDetail = Schemas["ComplaintDetail"];
export type ComplaintCategory = Schemas["ComplaintCategory"];
export type ComplaintCreate = Schemas["ComplaintCreate"];
export type ComplaintUpdate = Schemas["ComplaintUpdate"];
export type CommentOut = Schemas["CommentOut"];
export type PriorityLevel = Schemas["PriorityLevel"];

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

/** The body of `POST /devices/{id}/events`: one of ten shapes, told apart by `event_type`. */
export type EventBody =
  paths["/api/v1/devices/{device_id}/events"]["post"]["requestBody"]["content"]["application/json"];
