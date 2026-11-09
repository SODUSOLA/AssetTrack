/** No 0/O, 1/l/I: a password read out or typed from paper must not be ambiguous. */
const ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";

/**
 * A starting password for a new account or a reset: random from the browser's secure generator,
 * 16 characters (about 91 bits). It is shown to the administrator once and never stored here.
 */
export function generatePassword(length = 16, random: Crypto = crypto): string {
  const limit = 256 - (256 % ALPHABET.length); // reject the biased tail so every letter is equally likely
  const out: string[] = [];
  while (out.length < length) {
    for (const byte of random.getRandomValues(new Uint8Array(length * 2))) {
      if (byte < limit && out.length < length) out.push(ALPHABET[byte % ALPHABET.length]!);
    }
  }
  return out.join("");
}
