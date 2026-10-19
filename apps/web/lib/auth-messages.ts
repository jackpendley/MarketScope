/** What a person sees when sign-in fails. Wrong username and wrong password read the same, so the
 * page never reveals which accounts exist. */
export function signInErrorMessage(status: number | undefined): string {
  if (status === 429) return "Too many attempts. Wait a minute, then try again.";
  if (status === 401 || status === 400 || status === 403)
    return "That username or email and password don't match.";
  return "Sign-in failed. Check your connection and try again.";
}

/** Client-side checks before asking the server to change a password. Null when it looks fine. */
export function newPasswordProblem(
  next: string,
  confirm: string,
  current: string,
  min: number,
): string | null {
  if (next.length < min) return `Use at least ${min} characters.`;
  if (next !== confirm) return "The two new passwords don't match.";
  if (next === current) return "Choose a password different from the current one.";
  return null;
}
