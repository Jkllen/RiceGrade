/** To use your own logo, add frontend/public/ricegrade-logo.png and set LOGO_SRC. */
export const LOGO_SRC: string | null = null;

export function BrandLogo({small=false}:{small?:boolean}) {
  return LOGO_SRC
    ? <img className={`brand-logo${small ? ' small' : ''}`} src={LOGO_SRC} alt="" aria-hidden="true"/>
    : <span aria-hidden="true" className={`brand-mark${small ? ' small' : ''}`}/>;
}
