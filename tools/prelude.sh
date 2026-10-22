# Служебный файл сборки методички: `npx prisma migrate dev` спрашивает подтверждения и требует терминал,
# поэтому в сборке она запускается в псевдотерминале. Ответы: если на вход подан канал (echo n | …) — берётся он,
# иначе на каждый вопрос отвечаем «y». Из вывода убираются управляющие последовательности терминала.
_TOP0=$(readlink /proc/$$/fd/0)
_clean() { tr -d '\r' | sed -E "s/$(printf '\033')\\[[0-9;?]*[A-Za-z]//g" | sed -E '1{/^y$/d};s/\\$//' ; }
npx() {
  case "$*" in
    'prisma migrate dev'*)
      if [ "$(readlink /proc/$BASHPID/fd/0)" != "$_TOP0" ]; then
        timeout 600 script -qefc "$(command -v npx) $*" /dev/null | _clean
      else
        printf 'y\n' | timeout 600 script -qefc "$(command -v npx) $*" /dev/null | _clean
      fi ;;
    *) command npx "$@" ;;
  esac
}
