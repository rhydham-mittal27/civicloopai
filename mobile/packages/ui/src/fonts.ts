import { Poppins_400Regular, Poppins_500Medium, Poppins_600SemiBold, Poppins_700Bold, useFonts } from "@expo-google-fonts/poppins";

/** Loads Poppins. Returns true when the fonts are ready (or could not load, in which case the system font is used). */
export function useBrandFonts(): boolean {
  const [loaded, error] = useFonts({ Poppins_400Regular, Poppins_500Medium, Poppins_600SemiBold, Poppins_700Bold });
  return loaded || !!error;
}
