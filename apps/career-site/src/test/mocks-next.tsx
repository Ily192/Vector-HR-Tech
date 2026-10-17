// Sustitutos de `next/link` y `next/form` para jsdom: necesitan el router de Next,
// así que en los tests se renderizan como el <a> y el <form> que acaban siendo.
import type * as React from "react";

export function LinkFalso({
  children,
  href,
  ...props
}: React.PropsWithChildren<{ href: string } & React.AnchorHTMLAttributes<HTMLAnchorElement>>) {
  return (
    <a href={href} {...props}>
      {children}
    </a>
  );
}

export function FormFalso({
  children,
  action,
  ...props
}: React.PropsWithChildren<{ action: string } & React.FormHTMLAttributes<HTMLFormElement>>) {
  return (
    <form action={action} method="get" {...props}>
      {children}
    </form>
  );
}
