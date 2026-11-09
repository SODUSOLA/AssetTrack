import { isApiError } from "@/api/errors";

/** Plain-language text for errors a person is likely to meet. Anything else uses the server's own message. */
const BY_CODE: Record<string, string> = {
  INVALID_CREDENTIALS: "That email and password do not match.",
  RATE_LIMITED: "Too many attempts. Wait a minute, then try again.",
  FORBIDDEN: "You do not have permission to do that.",
  NOT_AUTHENTICATED: "Your session has ended. Please sign in again.",
  TOKEN_EXPIRED: "Your session has ended. Please sign in again.",
  NETWORK_ERROR: "Cannot reach the server. Check your connection and try again.",
  TIMEOUT: "The server took too long to answer. Try again.",
  INVALID_TRANSITION:
    "The status changed, so that step is no longer possible. The page now shows its current state.",
  ALREADY_ACKNOWLEDGED: "This has already been answered.",
  ACK_NOT_REQUIRED: "This event does not need an answer.",
  SERIAL_EXISTS: "Another device already has that serial number.",
  INVALID_OLD_PASSWORD: "The current password is not correct.",
  PASSWORD_UNCHANGED: "The new password must be different from the current one.",
  TICKET_NOT_ACTIVE:
    "That complaint is already resolved or closed, so engineering can no longer change it.",
  DEVICE_IN_REPAIR:
    "The device taken in for this complaint has not been returned yet. Return it to the unit first.",
  AWAITS_ACKNOWLEDGEMENT:
    "The returned device is waiting for the unit's answer. Answer on the device instead; that closes or reopens this complaint.",
  ASSIGNEE_REQUIRED: "Choose who will work on this complaint.",
  ASSIGNEE_INVALID: "The person must be an active engineer or the head of engineering.",
  COMMENT_REQUIRED: "Write a note first: it is recorded permanently.",
  COMMENT_WITHOUT_CHANGE: "A note needs a change to go with it.",
  DEVICE_DECOMMISSIONED: "That device has been decommissioned.",
  DEVICE_UNIT_MISMATCH: "That device is not with the unit the complaint is for.",
  UNIT_REQUIRED: "Choose the unit this complaint is for.",
  DEVICE_NOT_FOUND: "That device could not be found.",
  COMPLAINT_NOT_FOUND: "That complaint could not be found.",
  EVENT_NOT_FOUND: "That event could not be found.",
  COMPLAINT_UNIT_MISMATCH: "That complaint belongs to a different unit.",
  COMPLAINT_DEVICE_MISMATCH: "That complaint is about a different device.",
  INVALID_RANGE: "The start date must not be after the end date.",
  RANGE_TOO_LARGE: "Choose a period of five years or less.",
  INVALID_MIN: "Choose a minimum of 2 to 100 repairs.",
  INVALID_MONTH: "Choose a month, for example 2026-10.",
  EMAIL_TAKEN: "Another person already has that email address.",
  LAST_ADMIN: "At least one active Head of Engineering account must remain.",
  UNIT_EXISTS: "Another unit already has that name or code.",
  UNIT_NOT_ALLOWED: "Only a unit representative belongs to a unit.",
  USER_NOT_FOUND: "That person could not be found.",
  UNIT_NOT_FOUND: "That unit does not exist or is no longer active.",
};

export function describeError(error: unknown): string {
  if (isApiError(error)) return BY_CODE[error.code] ?? error.message;
  return "Something went wrong. Try again.";
}
