import { NavLink } from "react-router-dom";

const TABS = [
  { to: "/", label: "Home", end: true },
  { to: "/classes", label: "Classes", end: false },
  { to: "/profile", label: "Profile", end: false },
] as const;

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-[44px] items-center justify-center gap-2 px-3 text-sm font-medium ${
    isActive ? "text-slate-900" : "text-slate-500"
  }`;

/**
 * Bottom tab bar below 640px, persistent left nav at >=1024px.
 * Teacher tabs per plan §3: Home · Classes · Profile.
 */
export function AppNav() {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-10 flex border-t border-slate-200 bg-white lg:static lg:inset-auto lg:h-full lg:w-56 lg:flex-col lg:border-t-0 lg:border-r lg:py-4"
    >
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={linkClass}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
