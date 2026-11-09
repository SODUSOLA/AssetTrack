import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { isApiError } from "@/api/errors";
import { Brand } from "@/components/layout/Brand";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Fields";
import { Alert } from "@/components/ui/Feedback";
import { describeError } from "@/lib/messages";
import { useAuth } from "@/features/auth/authContext";
import s from "./LoginPage.module.css";

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter your email address")
    .pipe(z.email("Enter a valid email address")),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { login } = useAuth();
  const [problem, setProblem] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setFocus,
    resetField,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: Values) {
    setProblem(null);
    try {
      await login(values.email, values.password);
      // PublicOnly sends the user on to where they were going.
    } catch (error) {
      setProblem(describeError(error));
      if (isApiError(error) && error.code === "INVALID_CREDENTIALS") {
        resetField("password");
        setFocus("password");
      }
    }
  }

  return (
    <div className={s.page}>
      <aside className={s.brandPanel}>
        <Brand />
        <div className={s.pitch}>
          <h2 className={s.headline}>Every handover and every repair, on the record.</h2>
          <p>
            Devices, complaints and repairs, confirmed by the engineers who do the work and the
            units who receive it.
          </p>
        </div>
      </aside>

      <main className={s.formPanel}>
        <form className={s.form} onSubmit={handleSubmit(onSubmit)} noValidate>
          <h1 className={s.title}>Sign in</h1>
          <p className={s.lead}>Use the account the Head of Engineering created for you.</p>

          {problem && <Alert tone="error">{problem}</Alert>}

          <TextField
            label="Email address"
            type="email"
            autoComplete="username"
            inputMode="email"
            autoFocus
            error={errors.email?.message}
            {...register("email")}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register("password")}
          />
          <Button type="submit" variant="primary" loading={isSubmitting}>
            Sign in
          </Button>
        </form>
      </main>
    </div>
  );
}
