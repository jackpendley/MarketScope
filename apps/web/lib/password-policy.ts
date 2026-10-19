// Site password rule (MS-038b, ADR-049 amendment), chosen by Jack: at least 9 characters with at
// least one capital letter and one special character. One module, used by the auth server hook,
// the account CLI and the change-password form, so they can't disagree.

export const PASSWORD_MIN_LENGTH = 9;
export const PASSWORD_MAX_LENGTH = 128;
export const PASSWORD_RULE = `At least ${PASSWORD_MIN_LENGTH} characters, including a capital letter and a special character (such as ! ? # or %).`;

/** Why a password breaks the rule, or null when it's fine. */
export function passwordProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH)
    return `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
  if (password.length > PASSWORD_MAX_LENGTH)
    return `Use at most ${PASSWORD_MAX_LENGTH} characters.`;
  if (!/[A-Z]/.test(password)) return "Include at least one capital letter.";
  if (!/[^A-Za-z0-9\s]/.test(password))
    return "Include at least one special character, such as ! ? # or %.";
  return null;
}
