import { useState } from "react";
import { Link } from "react-router-dom";

export default function Register() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="glass-panel rounded-3xl p-6 sm:p-8">
          <div className="mb-6 text-center">
            <h1 className="font-space text-2xl font-bold text-white sm:text-3xl">
              Create Account
            </h1>
            <p className="mt-2 text-sm text-zinc-400">
              Join Konvy Accounts today
            </p>
          </div>

          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
            }}
          >
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">Username</label>
              <div className="relative">
                <i className="ri-user-line absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 text-sm"></i>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Choose a username"
                  className="h-12 w-full rounded-xl border border-white/15 bg-black/35 pl-11 pr-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">Email</label>
              <div className="relative">
                <i className="ri-mail-line absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 text-sm"></i>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="h-12 w-full rounded-xl border border-white/15 bg-black/35 pl-11 pr-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">Password</label>
              <div className="relative">
                <i className="ri-lock-line absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 text-sm"></i>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Create a password"
                  className="h-12 w-full rounded-xl border border-white/15 bg-black/35 pl-11 pr-11 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 cursor-pointer"
                >
                  <i className={`ri-${showPassword ? "eye-off" : "eye"}-line text-sm`}></i>
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">Confirm Password</label>
              <div className="relative">
                <i className="ri-lock-line absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 text-sm"></i>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
                  className="h-12 w-full rounded-xl border border-white/15 bg-black/35 pl-11 pr-4 text-sm text-white placeholder:text-zinc-500 transition focus-visible:shadow-focus"
                />
              </div>
            </div>

            <label className="flex items-start gap-2 text-xs text-zinc-400 cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5 h-3.5 w-3.5 rounded border-white/20 bg-black/35 accent-emerald-500"
              />
              <span>
                I agree to the{" "}
                <a href="#" className="text-emerald-400 hover:text-emerald-300 transition">
                  Terms of Service
                </a>{" "}
                and{" "}
                <a href="#" className="text-emerald-400 hover:text-emerald-300 transition">
                  Privacy Policy
                </a>
              </span>
            </label>

            <button
              type="submit"
              className="inline-flex h-12 w-full items-center justify-center rounded-xl px-4 text-sm font-medium transition focus-visible:shadow-focus disabled:opacity-50 bg-white text-black hover:bg-zinc-200 active:scale-[0.99] whitespace-nowrap cursor-pointer"
            >
              Create Account
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-zinc-400">
            Already have an account?{" "}
            <Link
              to="/login"
              className="font-medium text-emerald-400 hover:text-emerald-300 transition"
            >
              Sign In
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}